from odoo import models, fields, _
from odoo.tools import is_html_empty
from odoo.tools.misc import get_lang

import logging

_logger = logging.getLogger(__name__)

class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def action_notify(self):
        """Enviar notificaciones solo a usuarios que no hayan deshabilitado esta funcionalidad"""
        # Filtrar actividades cuyos usuarios TIENEN deshabilitadas las notificaciones
        activities_to_skip = self.filtered(
            lambda act: act.user_id and act.user_id.disable_activity_notifications
        )
        # Actividades que SÍ deben recibir notificación
        activities_to_notify = self - activities_to_skip
        
        # Llamar al método original SOLO para las actividades filtradas
        if activities_to_notify:
            return super(MailActivity, activities_to_notify).action_notify()
        return None


class ResUsers(models.Model):
    _inherit = 'res.users'

    disable_activity_notifications = fields.Boolean(
        string='Deshabilitar notificaciones de actividades',
        default=False,
        help='Si está marcado, el usuario no recibirá notificaciones por correo/electronico cuando se le asignen actividades.'
    )