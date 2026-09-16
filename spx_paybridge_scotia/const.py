PROVIDER_CODE = 'spx_paybridge_scotia'
PROTOCOL_VERSION = 1
RETURN_ROUTE = '/payment/spx_paybridge_scotia/return'
NOTIFY_ROUTE = '/payment/spx_paybridge_scotia/notify'
CHECKOUT_ROUTE = '/payment/spx_paybridge_scotia/checkout'
UNVERIFIED_ROUTE = '/payment/spx_paybridge_scotia/unverified'
CHECKOUT_TOKEN_TTL = 1800
DISPLAY_MODES = [('redirect', 'Direct redirect'), ('branded', 'Branded redirect page'),
                 ('embedded', 'Embedded payment page')]
GATEWAY_URLS = {
    'test': 'https://test.ipg-online.com/connect/gateway/processing',
    'live': 'https://www2.ipg-online.com/connect/gateway/processing',
}
CURRENCY_CODES = {
    'TTD': '780', 'USD': '840', 'EUR': '978', 'GBP': '826',
    'CAD': '124', 'BBD': '052', 'JMD': '388', 'XCD': '951',
    'BSD': '044', 'BZD': '084', 'GYD': '328', 'MXN': '484',
    'DOP': '214', 'PEN': '604', 'COP': '170', 'CRC': '188',
}
# All mapped currencies have two minor-unit decimal places. Availability must
# additionally be restricted to the currencies enabled for the merchant store.
MAX_CALLBACK_BYTES = 65536
MAX_CALLBACK_FIELDS = 200
