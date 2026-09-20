{
    'name': 'Real Estate Sale Contract',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'depends': ['sale_management', 'crm', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/sale_contract_views.xml',
        'views/sale_order_views.xml',
        'views/crm_lead_view.xml'
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
