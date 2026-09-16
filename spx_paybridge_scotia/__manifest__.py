{
    'name': 'Spxcorp PayBridge - Scotiabank eCom+',
    'version': '19.0.1.1.1',
    'category': 'Accounting/Payment Providers',
    'summary': 'Scotiabank hosted payments with native Odoo 19 Enterprise accounting',
    'description': '''
Scotiabank eCom+ hosted card payments for Odoo 19 Enterprise.
Uses Odoo payment transactions, customer payments, invoices, journals,
outstanding receipts, and the standard reconciliation workflow.
Includes separate test/live credentials, payment-attempt signature
verification, asynchronous bank notifications, and bank reference tracing.
Includes a Test Mode USD simulation override, the original SPXCORP branded
handoff, embedded hosted payment pages, and safe configuration diagnostics.
Works with the existing Store ID and Shared Secret; no extra bank feature
activation is required.
Gateway refunds, capture, voids, saved cards and recurring charges are not
advertised because this integration uses the hosted sale protocol only.
''',
    'author': 'Spxcorp Limited',
    'website': 'https://spxcorp.net',
    'license': 'LGPL-3',
    'depends': ['payment', 'account_payment', 'account_accountant'],
    'data': [
        'views/payment_scotiabank_templates.xml',
        'data/payment_provider_data.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'views/account_payment_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
}
