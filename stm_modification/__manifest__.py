{
    'name': 'STM Modification',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Professional Invoice Design Template',
    'author': 'Your Company',
    'depends': ['account', 'sale', 'product', 'stock', 'web'],
    'data': [
        'security/ir.model.access.csv',
	    'views/report_invoice.xml',
        'views/product_template_views.xml',
	    'views/account_statement_report.xml',
        'views/account_statement_template.xml',
        'wizard/account_statement_wizard_view.xml',
	    'views/product_category_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'account_statement_report/static/src/css/account_statement_report.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
