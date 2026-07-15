from odoo import models, fields, api, _
from odoo.exceptions import UserError
import pytz
from datetime import timedelta
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class HrUnjustifiedAbsenceWizard(models.TransientModel):
    _name = 'hr.unjustified.absence.wizard'
    _description = 'Verificador de Ausencias Injustificadas'

    # Selector de período rápido (mes/año)
    period_type = fields.Selection([
        ('month', 'Mes'),
        ('custom', 'Personalizado'),
    ], string='Tipo de período', default='month', required=True)
    
    month = fields.Selection(
        selection='_get_month_selection',
        string='Mes',
        default=lambda self: str(fields.Date.today().month)
    )
    year = fields.Integer(
        string='Año',
        default=lambda self: fields.Date.today().year,
        required=True
    )
    fortnight = fields.Selection([
        ('first', 'Primera quincena (1-15)'),
        ('second', 'Segunda quincena (16-fin)'),
    ], string='Quincena', default='first')
    
    # ✅ CORRECCIÓN: Quitar required=True (son calculados y readonly)
    date_from = fields.Date(
        string='Fecha Desde'
    )
    
    date_to = fields.Date(
        string='Fecha Hasta'
    )
    
    # ✅ CORRECCIÓN: Empleados vacíos por defecto (el usuario decide si filtrar)
    employee_ids = fields.Many2many(
        'hr.employee', 
        string='Empleados',
        default=lambda self: self.env['hr.employee']  # RecordSet vacío
    )
    line_ids = fields.One2many(
        'hr.unjustified.absence.line', 
        'wizard_id', 
        string='Ausencias Detectadas',
        readonly=True
    )
    
    # Estadísticas rápidas
    total_absences = fields.Integer('Total Ausencias', compute='_compute_stats')
    total_employees = fields.Integer('Empleados con Ausencias', compute='_compute_stats')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
    
        today = fields.Date.today()
    
        month = today.month
        year = today.year
    
        if month == 1:
            prev_month = 12
            prev_year = year - 1
        else:
            prev_month = month - 1
            prev_year = year
    
        res.update({
            'date_from': fields.Date.to_date(
                f'{prev_year}-{prev_month:02d}-21'
            ),
            'date_to': fields.Date.to_date(
                f'{year}-{month:02d}-20'
            ),
        })
    
        return res


    @api.onchange('period_type', 'month', 'year', 'fortnight')
    def _onchange_dates(self):
        for wizard in self:
            if wizard.period_type == 'custom':
                return
    
            if not wizard.month or not wizard.year:
                return
    
            month_int = int(wizard.month)
    
            if wizard.period_type == 'month':
                # 21 del mes anterior al 20 del actual
                if month_int == 1:
                    prev_month = 12
                    prev_year = wizard.year - 1
                else:
                    prev_month = month_int - 1
                    prev_year = wizard.year
    
                wizard.date_from = fields.Date.to_date(
                    f'{prev_year}-{prev_month:02d}-21'
                )
                wizard.date_to = fields.Date.to_date(
                    f'{wizard.year}-{month_int:02d}-20'
                )
    
            elif wizard.period_type == 'fortnight':
                base_date = fields.Date.to_date(
                    f'{wizard.year}-{month_int:02d}-01'
                )
    
                if wizard.fortnight == 'first':
                    wizard.date_from = base_date
                    wizard.date_to = base_date.replace(day=15)
                else:
                    wizard.date_from = base_date.replace(day=16)
                    next_month = base_date + relativedelta(months=1)
                    wizard.date_to = next_month - timedelta(days=1)

    @api.model
    def _get_month_selection(self):
        months = [
            ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'),
            ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'),
            ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre')
        ]
        return months

    @api.depends('period_type', 'month', 'year', 'fortnight')
    def _compute_dates(self):
        for wizard in self:
            if wizard.period_type == 'custom':
                # No modificar fechas ingresadas manualmente
                continue
            if wizard.period_type == 'month':
                # Período nómina: 21 del mes anterior al 20 del mes actual (inclusive)
                month_int = int(wizard.month)
                if month_int == 1:  # Enero → usar diciembre del año anterior
                    prev_month = 12
                    prev_year = wizard.year - 1
                else:
                    prev_month = month_int - 1
                    prev_year = wizard.year
                
                wizard.date_from = fields.Date.to_date(f'{prev_year}-{prev_month:02d}-21')
                wizard.date_to = fields.Date.to_date(f'{wizard.year}-{wizard.month}-20')
            elif wizard.period_type == 'fortnight':
                base_date = fields.Date.to_date(f'{wizard.year}-{wizard.month}-01')
                if wizard.fortnight == 'first':
                    wizard.date_from = base_date
                    wizard.date_to = base_date.replace(day=15)
                else:
                    wizard.date_from = base_date.replace(day=16)
                    next_month = base_date + relativedelta(months=1)
                    wizard.date_to = next_month - timedelta(days=1)
            else:  # custom
                wizard.date_from = fields.Date.today().replace(day=1)
                next_month = wizard.date_from + relativedelta(months=1)
                wizard.date_to = next_month - timedelta(days=1)

    @api.depends('line_ids')
    def _compute_stats(self):
        for wizard in self:
            wizard.total_absences = len(wizard.line_ids)
            wizard.total_employees = len(set(wizard.line_ids.mapped('employee_id.id')))

    def action_calculate_absences(self):
        """Calcula ausencias injustificadas - si employee_ids está vacío, usa TODOS los empleados"""
        self.ensure_one()
        
        # ✅ Validación explícita de fechas (en lugar de required=True)
        if not self.date_from or not self.date_to:
            raise UserError(_('Seleccione un período válido (mes/año o quincena).'))
        
        if self.date_from > self.date_to:
            raise UserError(_('La fecha "Desde" no puede ser mayor a la fecha "Hasta"'))
        
        # Limpiar líneas anteriores
        self.line_ids.unlink()
        
        lines_to_create = []
        tz_py = pytz.timezone('America/Asuncion')
        
        # ✅ CORRECCIÓN: Si no hay empleados seleccionados, usar TODOS
        employees = self.employee_ids if self.employee_ids else self.env['hr.employee'].search([
            ('active', '=', True),
            ('resource_id', '!=', False)
        ])
        
        _logger.info(f"Calculando ausencias desde {self.date_from} hasta {self.date_to} para {len(employees)} empleados")
        
        for employee in employees.filtered(lambda e: e.resource_id):
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', employee.id),
                ('state', 'in', ['open', 'close']),
                '|', ('date_end', '=', False), ('date_end', '>=', self.date_from),
                ('date_start', '<=', self.date_to),
            ], order='date_start desc', limit=1)
            
            if not contract:
                continue
                
            calendar = contract.resource_calendar_id or employee.resource_calendar_id or self.env.company.resource_calendar_id
            if not calendar:
                continue
            
            effective_start = max(contract.date_start, self.date_from)
            effective_end = min(contract.date_end or self.date_to, self.date_to)
            
            if effective_start > effective_end:
                continue
            
            dt_from = fields.Datetime.to_datetime(effective_start)
            dt_to = fields.Datetime.to_datetime(effective_end)
            local_from = tz_py.localize(dt_from.replace(hour=0, minute=0, second=0))
            local_to = tz_py.localize(dt_to.replace(hour=23, minute=59, second=59))
            
            intervals = calendar._work_intervals_batch(local_from, local_to, resources=employee.resource_id, tz=tz_py)
            att_intervals = intervals.get(employee.resource_id.id, [])
            
            workable_dates = set()
            for start, stop, _ in att_intervals:
                start_date = start.date()
                end_date = min(stop.date(), self.date_to)
            
                d = start_date
                while d <= end_date:
                    workable_dates.add(d)
                    d += timedelta(days=1)
                            
            if not workable_dates:
                continue
            holidays = self.env['resource.calendar.leaves'].search([
                ('resource_id', '=', False),
                ('date_from', '<=', local_to.astimezone(pytz.UTC).replace(tzinfo=None)),
                ('date_to', '>=', local_from.astimezone(pytz.UTC).replace(tzinfo=None)),
            ])
            holiday_dates = set()
            
            for leave in holidays:
                start = pytz.utc.localize(leave.date_from).astimezone(tz_py).date()
                stop = pytz.utc.localize(leave.date_to).astimezone(tz_py).date()
            
                d = start
                while d <= stop:
                    holiday_dates.add(d)
                    d += timedelta(days=1)
            _logger.info("Feriados")
            _logger.info(holiday_dates)
            workable_dates -= holiday_dates
            work_entries = self.env['hr.work.entry'].search([
                ('employee_id', '=', employee.id),
                ('active', '=', True),
                ('date_stop', '>=', fields.Datetime.to_datetime(effective_start)),
                ('date_start', '<=', fields.Datetime.to_datetime(effective_end) + timedelta(days=1)),
            ])
            
            covered_dates = set()
            for we in work_entries:
                start_utc = we.date_start
                stop_utc = we.date_stop
                start_local = pytz.utc.localize(start_utc).astimezone(tz_py).date()
                stop_local = pytz.utc.localize(stop_utc).astimezone(tz_py).date()
                
                d = start_local
                while d <= stop_local:
                    if effective_start <= fields.Date.from_string(str(d)) <= effective_end:
                        covered_dates.add(d)
                    d += timedelta(days=1)
            _logger.info("Fechas laborables")
            _logger.info(workable_dates)
            _logger.info("Fechas cubiertas")
            _logger.info(covered_dates)
            unjustified_dates = workable_dates - covered_dates
            
            for absence_date in sorted(unjustified_dates):
                lines_to_create.append({
                    'wizard_id': self.id,
                    'employee_id': employee.id,
                    'contract_id': contract.id,
                    'absence_date': absence_date,
                    'contract_start': contract.date_start,
                    'contract_end': contract.date_end,
                    'calendar_id': calendar.id,
                })
        
        if lines_to_create:
            self.env['hr.unjustified.absence.line'].create(lines_to_create)
        

    def action_reset(self):
        self.ensure_one()
        self.line_ids.unlink()
        # Resetear a valores por defecto (mes actual, empleados vacíos)
        default_vals = self.default_get(['period_type', 'month', 'year', 'fortnight'])
        self.write(default_vals)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class HrUnjustifiedAbsenceLine(models.TransientModel):
    _name = 'hr.unjustified.absence.line'
    _description = 'Línea de Ausencia Injustificada'
    _order = 'absence_date, employee_id'

    wizard_id = fields.Many2one('hr.unjustified.absence.wizard', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, readonly=True)
    contract_id = fields.Many2one('hr.contract', string='Contrato', readonly=True)
    absence_date = fields.Date(string='Fecha de Ausencia', required=True, readonly=True)
    contract_start = fields.Date(string='Inicio Contrato', readonly=True)
    contract_end = fields.Date(string='Fin Contrato', readonly=True)
    calendar_id = fields.Many2one('resource.calendar', string='Calendario', readonly=True)
    
    employee_identification_id = fields.Char(
        related='employee_id.identification_id', 
        string='C.I.', 
        readonly=True, 
        store=False
    )
    department_id = fields.Many2one(
        related='employee_id.department_id', 
        string='Departamento', 
        readonly=True, 
        store=False
    )
    job_title = fields.Char(
        related='employee_id.job_title',
        string='Puesto',
        readonly=True,
        store=False
    )

    def action_create_leave_request(self):
        self.ensure_one()
    
        leave_type = self.env['hr.leave.type'].search([
            ('active', '=', True)
        ], limit=1)
    
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nueva Solicitud'),
            'res_model': 'hr.leave',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_employee_id': self.employee_id.id,
                'default_holiday_status_id': leave_type.id if leave_type else False,
                'default_request_date_from': self.absence_date,
                'default_request_date_to': self.absence_date,
                'default_name': f'Justificación ausencia {self.absence_date}',
            }
        }