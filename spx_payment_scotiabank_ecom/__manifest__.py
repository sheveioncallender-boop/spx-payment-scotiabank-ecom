{
    'name': 'SPX Scotiabank eCom+ Payment Gateway',
    'version': '1.0.8',
    'category': 'Accounting/Payment Providers',
    'summary': 'Accept Scotiabank eCom+ / Fiserv hosted payments in Odoo website checkout and portal payment links.',
    'description': """
SPX Scotiabank eCom+ Payment Gateway
=====================================

Adds Scotiabank eCom+ as an Odoo payment provider using the Fiserv/IPG Connect hosted payment page flow.

Supported in this first version:
- Website checkout payment option
- Sale order / invoice portal payment link support through Odoo payment transactions
- Separate sandbox and live Store ID / Shared Secret credentials
- Sandbox/live gateway URLs
- Sandbox/live currency override, useful where sandbox is USD/840 while store is TTD/780
- Branded SPXCORP handoff page, direct redirect, and iframe display modes
- HMAC-SHA256 request hash generation
- Response hash validation
- Approved/failed/cancelled transaction handling
- Duplicate/late callback protection
- Payment transaction diagnostics and chatter notes

Refunds, captures, voids, tokenization, and recurring payments are intentionally not included yet because those require separate Fiserv REST API credentials.
    """,
    'author': 'Sheveion Callender / SPXCORP Limited',
    'website': 'https://spxcorp.com',
    'license': 'LGPL-3',
    'depends': ['payment', 'website_sale', 'account_payment'],
    'data': [
        'views/payment_scotiabank_templates.xml',
        'data/payment_provider_data.xml',
        'data/account_payment_method_data.xml',
        'data/payment_method_link_data.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'spx_payment_scotiabank_ecom/static/src/scss/scotiabank_ecom.scss',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
}
