# -*- coding: utf-8 -*-
{
    'name': 'Reporte de ausencias',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': " Reporte de ausencias",
    'description': " Reporte de ausencias de empleados basado en asistencias biométricas",
    'author': 'GonzaOdoo',
    'maintainer': 'GonzaOdoo',
    'website': "https://www.github.com",
    'depends': ['hr_attendance','mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/reporte_ausencia_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': True,
}
