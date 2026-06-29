# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .payment_provider import SCOTIABANK_ECOM_CODE

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    scotia_oid = fields.Char(string='Scotiabank Order ID', readonly=True, copy=False)
    scotia_ipg_transaction_id = fields.Char(string='Scotiabank IPG Transaction ID', readonly=True, copy=False)
    scotia_refnumber = fields.Char(string='Scotiabank Reference Number', readonly=True, copy=False)
    scotia_approval_code = fields.Char(string='Scotiabank Approval Code', readonly=True, copy=False)
    scotia_processor_response_code = fields.Char(string='Processor Response Code', readonly=True, copy=False)
    scotia_3ds_response = fields.Char(string='3-D Secure Response', readonly=True, copy=False)
    scotia_card_mask = fields.Char(string='Card Mask', readonly=True, copy=False)
    scotia_gateway_currency_numeric = fields.Char(string='Gateway Currency Code', readonly=True, copy=False)
    scotia_gateway_currency_alpha = fields.Char(string='Gateway Currency', readonly=True, copy=False)
    scotia_gateway_amount = fields.Float(string='Gateway Amount', readonly=True, copy=False)
    scotia_response_status = fields.Char(string='Scotiabank Response Status', readonly=True, copy=False)
    scotia_response_hash_validated = fields.Boolean(string='Response Hash Validated', readonly=True, copy=False)
    scotia_last_response = fields.Text(string='Last Scotiabank Response', readonly=True, copy=False)

    def _get_specific_rendering_values(self, processing_values):
        rendering_values = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != SCOTIABANK_ECOM_CODE:
            return rendering_values

        self.ensure_one()
        provider = self.provider_id
        base_url = self.get_base_url().rstrip('/')
        gateway_url = provider._scotia_get_gateway_url()
        tx_datetime, timezone_name = provider._scotia_get_tx_datetime()
        currency_numeric = provider._scotia_get_currency_numeric(self.currency_id)
        currency_alpha = provider._scotia_numeric_to_alpha(currency_numeric, self.currency_id)
        amount = f'{self.amount:.2f}'
        oid = provider._scotia_make_oid(self.reference)

        response_url = f'{base_url}/payment/scotiabank_ecom/return'
        parent_uri = f'{base_url}/payment/scotiabank_ecom/handoff'

        partner = self.partner_id
        country_code = partner.country_id.code or ''
        state_name = partner.state_id.name or ''
        lang = (partner.lang or self.env.lang or 'en_US').replace('-', '_')

        fields_dict = {
            'chargetotal': amount,
            'checkoutoption': 'combinedpage',
            'currency': currency_numeric,
            'hash_algorithm': 'HMACSHA256',
            'responseFailURL': response_url,
            'responseSuccessURL': response_url,
            'storename': provider._scotia_get_store_id(),
            'timezone': timezone_name,
            'txndatetime': tx_datetime,
            'txntype': 'sale',
            'oid': oid,
            'bname': partner.name or 'Customer',
            'email': partner.email or '',
            'phone': partner.phone or partner.mobile or '',
            'baddr1': partner.street or '',
            'baddr2': partner.street2 or '',
            'bcity': partner.city or '',
            'bstate': state_name,
            'bzip': partner.zip or '',
            'bcountry': country_code,
            'language': lang if lang in ('en_US', 'en_GB', 'es_ES', 'fr_FR') else 'en_GB',
            'comments': _('Odoo payment transaction %s') % self.reference,
            'threeDSRequestorChallengeIndicator': '1',
        }
        if provider.scotia_display_mode == 'iframe':
            fields_dict['parentUri'] = parent_uri

        fields_dict['hashExtended'] = provider._scotia_generate_extended_hash(fields_dict)

        self.write({
            'scotia_oid': oid,
            'scotia_gateway_currency_numeric': currency_numeric,
            'scotia_gateway_currency_alpha': currency_alpha,
            'scotia_gateway_amount': self.amount,
        })

        if provider.scotia_debug:
            provider.sudo().write({
                'scotia_last_diagnostic': _(
                    'Prepared Scotiabank eCom+ payment. Reference: %(reference)s | Amount: %(amount)s %(currency)s | Gateway currency code: %(numeric)s | Mode: %(mode)s'
                ) % {
                    'reference': self.reference,
                    'amount': amount,
                    'currency': currency_alpha,
                    'numeric': currency_numeric,
                    'mode': provider.state,
                }
            })

        special_inputs = {
            '_spx_gateway_url': gateway_url,
            '_spx_display_mode': provider.scotia_display_mode,
            '_spx_tx_reference': self.reference,
            '_spx_logo_url': provider.scotia_logo_url or '/spx_payment_scotiabank_ecom/static/src/img/spxcorp_logo_white.png',
            '_spx_header_color': provider.scotia_header_color or '#07101f',
            '_spx_button_color': provider.scotia_button_color or '#0055a4',
            '_spx_background_color': provider.scotia_background_color or '#f4f7fb',
            '_spx_handoff_message': provider.scotia_handoff_message or '',
            '_spx_loading_message': provider.scotia_loading_message or '',
            '_spx_show_powered_by': '1' if provider.scotia_show_powered_by else '0',
            '_spx_amount_display': f'{amount} {currency_alpha}',
        }

        if provider.scotia_display_mode == 'direct':
            api_url = gateway_url
            all_inputs = fields_dict
        else:
            api_url = f'{base_url}/payment/scotiabank_ecom/handoff'
            all_inputs = {**fields_dict, **special_inputs}

        rendering_values.update({
            'api_url': api_url,
            'inputs': sorted(all_inputs.items()),
        })
        return rendering_values

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        if provider_code != SCOTIABANK_ECOM_CODE:
            return super()._search_by_reference(provider_code, payment_data)
        reference = payment_data.get('oid') or payment_data.get('reference') or payment_data.get('merchantTransactionId')
        if not reference:
            _logger.warning('Scotiabank eCom+ response missing oid/reference.')
            return self
        tx = self.search([
            ('provider_code', '=', SCOTIABANK_ECOM_CODE),
            '|', ('reference', '=', reference), ('scotia_oid', '=', reference),
        ], limit=1)
        if not tx:
            _logger.warning('No Scotiabank eCom+ transaction found for oid/reference %s.', reference)
        return tx

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code != SCOTIABANK_ECOM_CODE:
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get('oid') or payment_data.get('reference') or payment_data.get('merchantTransactionId')

    def _extract_amount_data(self, payment_data):
        if self.provider_code != SCOTIABANK_ECOM_CODE:
            return super()._extract_amount_data(payment_data)
        # We validate gateway numeric currency manually because sandbox override can intentionally differ
        # from the Odoo transaction currency, e.g. Odoo TTD but Scotiabank sandbox USD/840.
        return None

    def _apply_updates(self, payment_data):
        if self.provider_code != SCOTIABANK_ECOM_CODE:
            return super()._apply_updates(payment_data)

        self.ensure_one()
        provider = self.provider_id
        status = (payment_data.get('status') or '').upper()
        approval_code = payment_data.get('approval_code') or ''
        is_approved = status == 'APPROVED' or approval_code.startswith('Y:') or payment_data.get('processor_response_code') == '00'

        # Duplicate/late callback guard: never downgrade a completed transaction.
        if self.state == 'done' and not is_approved:
            self._scotia_message_post(_('Ignored duplicate/late failed Scotiabank response because transaction is already done.'))
            return

        response_hash_valid = provider._scotia_validate_response_hash(payment_data)
        if provider.scotia_require_response_hash and not response_hash_valid:
            self.write({
                'scotia_response_status': status or 'HASH_FAILED',
                'scotia_response_hash_validated': False,
                'scotia_last_response': str(payment_data),
            })
            self._set_error(_('Scotiabank response hash validation failed. The payment was not accepted.'))
            self._scotia_message_post(_('Scotiabank eCom+ response hash validation failed.'))
            return

        amount_ok = True
        currency_ok = True
        if payment_data.get('chargetotal'):
            try:
                amount_ok = abs(float(payment_data.get('chargetotal')) - float(self.scotia_gateway_amount or self.amount)) < 0.01
            except Exception:
                amount_ok = False
        if self.scotia_gateway_currency_numeric and payment_data.get('currency'):
            currency_ok = str(payment_data.get('currency')) == str(self.scotia_gateway_currency_numeric)

        if not amount_ok or not currency_ok:
            self.write({
                'scotia_response_status': status or 'AMOUNT_CURRENCY_MISMATCH',
                'scotia_response_hash_validated': response_hash_valid,
                'scotia_last_response': str(payment_data),
            })
            self._set_error(_('Scotiabank amount/currency validation failed.'))
            self._scotia_message_post(_(
                'Scotiabank eCom+ amount/currency validation failed. Expected %(amount)s %(currency)s. Received %(received_amount)s %(received_currency)s.'
            ) % {
                'amount': self.scotia_gateway_amount or self.amount,
                'currency': self.scotia_gateway_currency_numeric or self.currency_id.name,
                'received_amount': payment_data.get('chargetotal'),
                'received_currency': payment_data.get('currency'),
            })
            return

        vals = {
            'provider_reference': payment_data.get('ipgTransactionId') or payment_data.get('refnumber') or payment_data.get('endpointTransactionId'),
            'scotia_response_status': status,
            'scotia_ipg_transaction_id': payment_data.get('ipgTransactionId'),
            'scotia_refnumber': payment_data.get('refnumber'),
            'scotia_approval_code': approval_code,
            'scotia_processor_response_code': payment_data.get('processor_response_code'),
            'scotia_3ds_response': payment_data.get('response_code_3dsecure'),
            'scotia_card_mask': payment_data.get('cardnumber'),
            'scotia_response_hash_validated': response_hash_valid,
            'scotia_last_response': str(payment_data),
        }
        self.write(vals)

        if is_approved:
            self._set_done()
            self._scotia_message_post(_(
                'Scotiabank eCom+ payment approved.<br/>Amount: %(amount).2f %(currency)s<br/>Transaction ID: %(txid)s<br/>Approval Code: %(approval)s<br/>Card: %(card)s'
            ) % {
                'amount': self.scotia_gateway_amount or self.amount,
                'currency': self.scotia_gateway_currency_alpha or self.currency_id.name,
                'txid': self.scotia_ipg_transaction_id or self.provider_reference or '',
                'approval': approval_code,
                'card': self.scotia_card_mask or '',
            })
        elif status in ('CANCELLED', 'CANCELED') or 'cancel' in (payment_data.get('fail_reason') or '').lower():
            self._set_canceled(provider._scotia_get_friendly_error(payment_data))
            self._scotia_message_post(_('Scotiabank eCom+ payment cancelled.'))
        else:
            message = provider._scotia_get_friendly_error(payment_data)
            self._set_error(message)
            self._scotia_message_post(_(
                'Scotiabank eCom+ payment failed.<br/>Status: %(status)s<br/>Reason: %(reason)s<br/>Fail Code: %(code)s'
            ) % {
                'status': status or 'FAILED',
                'reason': payment_data.get('fail_reason') or approval_code,
                'code': payment_data.get('fail_rc') or '',
            })

    def _scotia_message_post(self, body):
        try:
            self.message_post(body=body)
        except Exception:
            _logger.info('Scotiabank transaction note: %s', body)
