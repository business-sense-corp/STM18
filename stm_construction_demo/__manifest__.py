# -*- coding: utf-8 -*-
{
    'name': 'STM Construction & Real Estate Executive Demo',
    'version': '18.0.1.0.0',
    'category': 'Construction',
    'summary': 'المقاولات والتطوير العقاري — لوحة الإدارة التنفيذية، المقايسات، المستخلصات، والمساعد الذكي',
    'description': """
        Pre-Sales Executive Demo on Odoo 18 Enterprise covering:
        1. Procurement & Build (BOQ / Project Charter / Site Material Requests)
        2. Contracting & Progress Certificates (Vendor & Customer + Retention + Accounting + PDF)
        3. Real Estate Sales Bridge (Simulated Online Booking + Unit Readiness & Handover)
        4. Executive OWL 2 Dashboard (5 KPI Groups + 10-Unit Block Margin) & Interactive AI Assistant
    """,
    'author': 'Business Sense Corp / STM',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'hr',
        'purchase',
        'stock',
        'sale_management',
        'account',
        'real_estate_contract',
        'sh_pdc',
        'stm_modification',
    ],
    'data': [
        # === S0 (Base Security & Navigation) ===
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/menus.xml',
        # === S1 ===
        'data/boq_sequence.xml',
        'views/boq_views.xml',
        'views/project_views.xml',
        'views/site_request_views.xml',
        'report/boq_report.xml',
        # === S2 ===
        # === S3 ===
        # === S4 ===
    ],
    'assets': {
        'web.assets_backend': [
            # === S1 ===
            # === S2 ===
            # === S3 ===
            # === S4 ===
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
}
