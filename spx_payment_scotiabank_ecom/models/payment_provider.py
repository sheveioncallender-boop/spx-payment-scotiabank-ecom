# -*- coding: utf-8 -*-

import base64
import hashlib
import hmac
import logging
import re
from datetime import datetime

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

SCOTIABANK_ECOM_CODE = 'scotiabank_ecom'

CURRENCY_ALPHA_TO_NUMERIC = {
    'TTD': '780',
    'USD': '840',
    'EUR': '978',
    'GBP': '826',
    'CAD': '124',
    'BBD': '052',
    'JMD': '388',
    'XCD': '951',
}

CURRENCY_NUMERIC_TO_ALPHA = {value: key for key, value in CURRENCY_ALPHA_TO_NUMERIC.items()}


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[(SCOTIABANK_ECOM_CODE, 'Scotiabank eCom+')],
        ondelete={SCOTIABANK_ECOM_CODE: 'set default'},
    )

    scotia_store_id = fields.Char(
        string='Store ID / Store Name',
        help='Scotiabank/Fiserv Store ID provided for the hosted payment page integration.',
    )
    scotia_shared_secret = fields.Char(
        string='Shared Secret',
        groups='base.group_system',
        help='Shared Secret used to generate and validate HMAC-SHA256 hashes. Keep this private.',
    )
    scotia_sandbox_gateway_url = fields.Char(
        string='Sandbox Gateway URL',
        default='https://test.ipg-online.com/connect/gateway/processing',
    )
    scotia_live_gateway_url = fields.Char(
        string='Live Gateway URL',
        default='https://www2.ipg-online.com/connect/gateway/processing',
    )
    scotia_sandbox_currency_override = fields.Char(
        string='Sandbox Currency Code Override',
        size=3,
        help='Optional numeric ISO currency code to send in test mode. Example: 840 for USD. This does not convert the amount.',
    )
    scotia_live_currency_override = fields.Char(
        string='Live Currency Code Override',
        size=3,
        help='Optional numeric ISO currency code to send in live mode. Leave blank to use the Odoo transaction currency.',
    )
    scotia_timezone = fields.Selection(
        selection=[
            ('America/Port_of_Spain', 'America/Port_of_Spain'),
            ('America/New_York', 'America/New_York'),
            ('America/Mexico_City', 'America/Mexico_City'),
            ('Europe/London', 'Europe/London'),
            ('UTC', 'UTC'),
        ],
        string='Gateway Timezone',
        default='America/Port_of_Spain',
        help='Timezone used for txndatetime. If invalid, the module falls back to UTC.',
    )
    scotia_display_mode = fields.Selection(
        selection=[
            ('handoff', 'SPXCORP branded handoff page'),
            ('iframe', 'Embedded iframe page'),
            ('direct', 'Direct hosted-page redirect'),
        ],
        string='Payment Display Mode',
        default='handoff',
        required=True,
    )
    scotia_payment_title = fields.Char(
        string='Checkout Payment Title',
        default='Scotiabank eCom+',
    )
    scotia_payment_description = fields.Text(
        string='Checkout Payment Description',
        default='Pay securely with your Credit or Debit Card through Scotiabank eCom+.',
    )
    scotia_trust_message = fields.Char(
        string='Checkout Trust Message',
        default='Payments are securely processed by Scotiabank eCom+.',
    )
    scotia_show_card_logos = fields.Boolean(
        string='Show Card Badge Text',
        default=True,
        help='Show Visa / Mastercard text badges in the checkout description and handoff page.',
    )
    scotia_logo_url = fields.Char(
        string='Handoff Logo URL',
        help='Optional logo URL for the branded handoff page. Leave blank to use the SPXCORP logo included in the module.',
    )
    scotia_header_color = fields.Char(string='Header Color', default='#07101f')
    scotia_button_color = fields.Char(string='Button Color', default='#0055a4')
    scotia_background_color = fields.Char(string='Background Color', default='#f4f7fb')
    scotia_handoff_message = fields.Text(
        string='Handoff Message',
        default='You are being securely connected to Scotiabank eCom+ to complete your payment.',
    )
    scotia_loading_message = fields.Char(
        string='Loading Message',
        default='Loading secure Scotiabank eCom+ payment form…',
    )
    scotia_show_powered_by = fields.Boolean(
        string='Show Powered by SPXCORP',
        default=True,
    )
    scotia_require_response_hash = fields.Boolean(
        string='Require Response Hash Validation',
        default=True,
        help='Recommended. If enabled, responses without a valid response_hash are rejected.',
    )
    scotia_debug = fields.Boolean(string='Debug Logging', default=False)
    scotia_last_diagnostic = fields.Text(string='Last Diagnostic', readonly=True)

    def _compute_feature_support_fields(self):
        """Scotiabank hosted form v1 supports only sale payments in this module."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == SCOTIABANK_ECOM_CODE).update({
            'support_express_checkout': False,
            'support_manual_capture': False,
            'support_refund': None,
            'support_tokenization': False,
        })

    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.code != SCOTIABANK_ECOM_CODE:
            return super()._get_default_payment_method_codes()
        return {'card'}

    def _get_redirect_form_view(self, is_validation=False):
        self.ensure_one()
        if self.code != SCOTIABANK_ECOM_CODE:
            return super()._get_redirect_form_view(is_validation=is_validation)
        return self.env.ref('spx_payment_scotiabank_ecom.redirect_form_scotiabank_ecom')

    def _get_removal_values(self):
        values = super()._get_removal_values()
        values.update({
            'scotia_store_id': False,
            'scotia_shared_secret': False,
            'scotia_last_diagnostic': False,
        })
        return values

    # -------------------------------------------------------------------------
    # Scotiabank / Fiserv helpers
    # -------------------------------------------------------------------------

    def _scotia_get_gateway_url(self):
        self.ensure_one()
        return self.scotia_sandbox_gateway_url if self.state == 'test' else self.scotia_live_gateway_url

    def _scotia_get_currency_numeric(self, currency):
        self.ensure_one()
        override = self.scotia_sandbox_currency_override if self.state == 'test' else self.scotia_live_currency_override
        if override:
            cleaned = re.sub(r'[^0-9]', '', override or '')
            if len(cleaned) != 3:
                raise ValidationError(_('The Scotiabank currency override must be a 3-digit numeric ISO code, e.g. 840 or 780.'))
            return cleaned
        numeric = CURRENCY_ALPHA_TO_NUMERIC.get(currency.name)
        if not numeric:
            raise ValidationError(_(
                'Unsupported currency %s for Scotiabank eCom+. Add a numeric currency override on the provider.'
            ) % currency.name)
        return numeric

    def _scotia_numeric_to_alpha(self, numeric_code, fallback_currency=None):
        return CURRENCY_NUMERIC_TO_ALPHA.get(numeric_code) or (fallback_currency.name if fallback_currency else numeric_code)

    def _scotia_get_tx_datetime(self):
        self.ensure_one()
        timezone_name = self.scotia_timezone or 'UTC'
        try:
            timezone = pytz.timezone(timezone_name)
        except Exception:
            _logger.warning('Invalid Scotiabank timezone %s. Falling back to UTC.', timezone_name)
            timezone_name = 'UTC'
            timezone = pytz.UTC
        return datetime.now(timezone).strftime('%Y:%m:%d-%H:%M:%S'), timezone_name

    def _scotia_make_oid(self, reference):
        reference = reference or ''
        oid = re.sub(r'[^A-Za-z0-9\-]', '-', reference).strip('-')
        return oid[:78] or 'ODOO-TX'

    def _scotia_generate_extended_hash(self, fields_dict):
        self.ensure_one()
        if not self.scotia_shared_secret:
            raise ValidationError(_('Please configure the Scotiabank Shared Secret before enabling payments.'))
        values = []
        for key in sorted(fields_dict.keys()):
            if key in ('hashExtended', 'sharedsecret'):
                continue
            value = fields_dict.get(key)
            if value is None or value == '':
                continue
            values.append(str(value))
        hash_string = '|'.join(values)
        digest = hmac.new(
            self.scotia_shared_secret.encode('utf-8'),
            hash_string.encode('utf-8'),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode('ascii')

    def _scotia_validate_response_hash(self, payment_data):
        self.ensure_one()
        response_hash = payment_data.get('response_hash')
        if not response_hash:
            return not self.scotia_require_response_hash
        parts = [
            payment_data.get('approval_code', ''),
            payment_data.get('chargetotal', ''),
            payment_data.get('currency', ''),
            payment_data.get('txndatetime', ''),
            payment_data.get('storename', ''),
        ]
        hash_string = '|'.join(str(part) for part in parts)
        digest = hmac.new(
            (self.scotia_shared_secret or '').encode('utf-8'),
            hash_string.encode('utf-8'),
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(digest).decode('ascii')
        return hmac.compare_digest(expected, response_hash)

    def _scotia_get_friendly_error(self, payment_data):
        fail_rc = str(payment_data.get('fail_rc') or '')
        fail_reason = payment_data.get('fail_reason') or payment_data.get('processor_response_message') or ''
        approval_code = payment_data.get('approval_code') or ''
        if fail_rc == '50653' or 'invalid currency' in fail_reason.lower():
            return _('This store is not configured for the selected gateway currency. Please contact the merchant.')
        if 'timeout' in fail_reason.lower():
            return _('The bank response timed out. Please try again.')
        if 'cancel' in fail_reason.lower() or 'abort' in fail_reason.lower():
            return _('The payment was cancelled. You can try again.')
        if approval_code.startswith('N:'):
            return _('Your payment was not approved. Please try another card or contact your bank.')
        return _('Payment was not completed. Please try again or use another card.')
