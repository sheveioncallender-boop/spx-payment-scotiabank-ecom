{
    'name': 'Spxcorp PayBridge - Native POS Completion',
    'version': '19.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Refresh confirmed Scotia payments through native Odoo POS hooks',
    'author': 'Spxcorp Limited',
    'license': 'LGPL-3',
    'depends': ['spx_paybridge_scotia', 'pos_online_payment'],
    'assets': {
        'point_of_sale.assets_prod': [
            'spx_paybridge_scotia_pos/static/src/online_payment.js',
        ],
    },
    'auto_install': True,
    'installable': True,
    'application': False,
}
