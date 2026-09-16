import hashlib
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import SQL

from .. import const, gateway

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    scotia_protocol_version = fields.Integer(readonly=True, copy=False)
    scotia_environment = fields.Selection(
        [('test', 'Test'), ('live', 'Live')], string='Scotiabank Environment', readonly=True, copy=False,
    )
    scotia_oid = fields.Char(string='Bank Order Reference', readonly=True, copy=False, index=True)
    scotia_request_datetime = fields.Char(string='Original Request Time (UTC)', readonly=True, copy=False)
    scotia_gateway_store_id = fields.Char(string='Store ID Used', readonly=True, copy=False)
    scotia_request_amount = fields.Char(string='Original Amount', readonly=True, copy=False)
    scotia_gateway_currency_numeric = fields.Char(string='ISO Currency Code', readonly=True, copy=False)
    scotia_gateway_currency_alpha = fields.Char(string='Gateway Currency', readonly=True, copy=False)
    scotia_gateway_amount = fields.Float(string='Gateway Amount', readonly=True, copy=False)
    scotia_ipg_transaction_id = fields.Char(string='Reported Bank Transaction ID', readonly=True, copy=False)
    scotia_refnumber = fields.Char(string='Reported Bank Reference', readonly=True, copy=False)
    scotia_approval_code = fields.Char(string='Verified Approval Code', readonly=True, copy=False)
    scotia_processor_response_code = fields.Char(string='Reported Processor Code', readonly=True, copy=False)
    scotia_3ds_response = fields.Char(string='Reported 3-D Secure Result', readonly=True, copy=False)
    scotia_card_mask = fields.Char(string='Card Last Four', readonly=True, copy=False)
    scotia_card_brand = fields.Char(string='Card Brand', readonly=True, copy=False)
    scotia_response_status = fields.Char(string='Verified Payment Result', readonly=True, copy=False)
    scotia_response_hash_validated = fields.Boolean(string='Signature Verified', readonly=True, copy=False)
    scotia_signature_type = fields.Selection(
        [('return', 'Customer return'), ('notification', 'Bank notification')],
        readonly=True, copy=False, string='Signature Type',
    )
    scotia_last_fingerprint = fields.Char(readonly=True, copy=False)
    scotia_notification_received_at = fields.Datetime(string='Bank Notification Received', readonly=True, copy=False)
    scotia_return_received_at = fields.Datetime(string='Customer Return Received', readonly=True, copy=False)

    _scotia_unique_attempt_time = models.Constraint(
        'UNIQUE(scotia_gateway_store_id, scotia_request_datetime)',
        'Each Scotiabank store must use a unique original request timestamp.',
    )

    def _scotia_lock(self):
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute(SQL('SELECT id FROM payment_transaction WHERE id = %s FOR UPDATE', self.id))
        self.invalidate_recordset()

    def _scotia_allocate_request_time(self, store_id):
        """Reserve a real UTC second per Store ID, across companies/providers.

        Fiserv's standard signature does not include oid. A unique persisted
        request time closes same-amount cross-order replays inside this database.
        Serialize starts using the same store and wait for the next real second
        on collision; never send invented future timestamps to the gateway.
        """
        key = int.from_bytes(hashlib.sha256(('scotia:' + store_id).encode()).digest()[:8], 'big', signed=True)
        self.env.cr.execute(SQL('SELECT pg_advisory_xact_lock(%s)', key))
        for _attempt in range(3):
            now = datetime.now(timezone.utc)
            stamp = now.strftime('%Y:%m:%d-%H:%M:%S')
            if not self.sudo().search_count([
                ('scotia_gateway_store_id', '=', store_id), ('scotia_request_datetime', '=', stamp),
            ], limit=1):
                return stamp
            time.sleep(max(0.01, 1.01 - now.microsecond / 1_000_000))
        raise ValidationError(_('A payment is starting for this store. Please try again in a moment.'))

    def _get_specific_rendering_values(self, processing_values):
        values = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != const.PROVIDER_CODE:
            return values
        self.ensure_one()
        self._scotia_lock()
        if self.operation != 'online_redirect' or self.state not in ('draft', 'pending'):
            raise ValidationError(_('Start a new card payment from the order or invoice.'))
        provider = self.provider_id.sudo()
        base_url = provider._scotia_check_configuration()
        if self.currency_id not in provider.available_currency_ids or self.currency_id.name not in const.CURRENCY_CODES:
            raise ValidationError(_('This currency is not enabled for the Scotiabank provider.'))
        if self.currency_id.decimal_places != 2:
            raise ValidationError(_('This Scotiabank integration requires a currency with two decimal places.'))
        try:
            amount = gateway.amount_string(self.amount)
        except gateway.InvalidResponse as exc:
            raise ValidationError(_('The payment must have a positive amount with at most two decimal places.')) from exc
        environment = 'test' if provider.state == 'test' else 'live'
        store, secret = provider._scotia_credentials(environment)
        if self.scotia_protocol_version:
            # One transaction represents one immutable bank attempt. Never silently
            # change credentials, amount or timestamp when a form is rendered again.
            if (self.scotia_environment != environment or self.scotia_gateway_store_id != store
                    or self.scotia_request_amount != amount
                    or self.scotia_gateway_currency_alpha != self.currency_id.name):
                raise ValidationError(_('This payment attempt changed. Start a new payment from the document.'))
        else:
            prefix = re.sub(r'[^A-Za-z0-9-]', '-', self.reference).strip('-')[:40] or 'ODOO'
            self.write({
                'scotia_protocol_version': const.PROTOCOL_VERSION,
                'scotia_environment': environment,
                'scotia_oid': prefix + '-' + uuid.uuid4().hex,
                'scotia_request_datetime': self._scotia_allocate_request_time(store),
                'scotia_request_amount': amount,
                'scotia_gateway_store_id': store,
                'scotia_gateway_amount': self.amount,
                'scotia_gateway_currency_numeric': const.CURRENCY_CODES[self.currency_id.name],
                'scotia_gateway_currency_alpha': self.currency_id.name,
            })
        partner = self.partner_id
        parameters = {
            'chargetotal': self.scotia_request_amount,
            'checkoutoption': 'combinedpage',
            'currency': self.scotia_gateway_currency_numeric,
            'hash_algorithm': 'HMACSHA256',
            'oid': self.scotia_oid,
            'responseSuccessURL': base_url + const.RETURN_ROUTE,
            'responseFailURL': base_url + const.RETURN_ROUTE,
            'transactionNotificationURL': base_url + const.NOTIFY_ROUTE,
            'storename': self.scotia_gateway_store_id,
            'timezone': 'UTC',
            'txndatetime': self.scotia_request_datetime,
            'txntype': 'sale',
            'bname': (partner.name or 'Customer')[:96],
            'email': (self.partner_email or '')[:254],
            'phone': (self.partner_phone or '')[:32],
            'baddr1': (partner.street or '')[:96],
            'baddr2': (partner.street2 or '')[:96],
            'bcity': (partner.city or '')[:96],
            'bstate': (partner.state_id.name or '')[:96],
            'bzip': (partner.zip or '')[:24],
            'bcountry': partner.country_id.code or '',
        }
        parameters = {key: value for key, value in parameters.items() if value != ''}
        parameters['hashExtended'] = gateway.request_hash(parameters, secret)
        # Odoo owns the redirect form submission and subsequent status polling.
        # Keep the transaction draft while at the gateway, as native redirect
        # providers do; only a signed WAITING response sets pending.
        return {**values, 'api_url': const.GATEWAY_URLS[environment], 'inputs': sorted(parameters.items())}

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        if provider_code == const.PROVIDER_CODE:
            return payment_data.get('payload', {}).get('oid')
        return super()._extract_reference(provider_code, payment_data)

    @api.model
    def _search_by_reference(self, provider_code, payment_data):
        if provider_code != const.PROVIDER_CODE:
            return super()._search_by_reference(provider_code, payment_data)
        oid = self._extract_reference(provider_code, payment_data)
        if not oid or not isinstance(oid, str) or len(oid) > 78:
            return self.browse()
        transactions = self.search([
            ('provider_code', '=', const.PROVIDER_CODE), ('scotia_oid', '=', oid),
            ('scotia_protocol_version', '=', const.PROTOCOL_VERSION),
        ], limit=2)
        return transactions if len(transactions) == 1 else self.browse()

    def _scotia_verify(self, payment_data):
        self.ensure_one()
        if (self.provider_code != const.PROVIDER_CODE
                or self.scotia_protocol_version != const.PROTOCOL_VERSION
                or self.operation != 'online_redirect'):
            raise ValidationError(_('This is not a current Scotiabank payment attempt.'))
        expected = gateway.ExpectedPayment(
            oid=self.scotia_oid, amount=self.scotia_request_amount,
            currency=self.scotia_gateway_currency_numeric,
            txndatetime=self.scotia_request_datetime, store_id=self.scotia_gateway_store_id,
        )
        try:
            return gateway.verify_response(
                payment_data.get('payload', {}),
                self.provider_id.sudo()._scotia_response_secrets(self.scotia_environment),
                expected, source=payment_data.get('source'),
            )
        except gateway.InvalidResponse as exc:
            # Log only a fixed reason and Odoo ID, never a body, card data or signature.
            _logger.warning('Scotiabank message rejected for transaction %s: %s', self.id, str(exc))
            raise ValidationError(_('The bank response could not be verified.')) from exc

    def _process(self, provider_code, payment_data):
        if provider_code != const.PROVIDER_CODE:
            return super()._process(provider_code, payment_data)
        tx = self or self._search_by_reference(provider_code, payment_data)
        if not tx:
            return tx
        tx._scotia_lock()
        tx._scotia_verify(payment_data)  # Authenticate BEFORE Odoo can update any state.
        return super(PaymentTransaction, tx)._process(provider_code, payment_data)

    def _extract_amount_data(self, payment_data):
        if self.provider_code != const.PROVIDER_CODE:
            return super()._extract_amount_data(payment_data)
        return {
            'amount': float(payment_data['payload']['chargetotal']),
            'currency_code': self.scotia_gateway_currency_alpha, 'precision_digits': 2,
        }

    def _apply_updates(self, payment_data):
        if self.provider_code != const.PROVIDER_CODE:
            return super()._apply_updates(payment_data)
        self.ensure_one()
        result = self._scotia_verify(payment_data)
        source = payment_data['source']
        received_field = ('scotia_notification_received_at' if source == 'notification'
                          else 'scotia_return_received_at')
        if not self[received_field]:
            self[received_field] = fields.Datetime.now()
        if self.state == 'done' or self.scotia_last_fingerprint == result.fingerprint:
            return  # No repeated payment, changed references, or terminal-state downgrade.
        if self.state in ('error', 'cancel') and result.outcome != 'done':
            return
        self.write({
            # The merchant order reference is stable, present at the bank, and
            # signed in our request. Standard bank signatures do not cover IPG IDs.
            'provider_reference': self.scotia_oid,
            'scotia_ipg_transaction_id': result.transaction_id,
            'scotia_refnumber': result.reference_number,
            'scotia_approval_code': result.approval_code,
            'scotia_processor_response_code': result.processor_code,
            'scotia_3ds_response': result.three_ds_result,
            'scotia_card_mask': result.card_last4,
            'scotia_card_brand': result.card_brand,
            'scotia_response_status': result.status,
            'scotia_response_hash_validated': True,
            'scotia_signature_type': result.signature_type,
            'scotia_last_fingerprint': result.fingerprint,
        })
        if result.outcome == 'done':
            self._set_done(extra_allowed_states=('cancel',))
        elif result.outcome == 'pending':
            self._set_pending(state_message=_('Waiting for Scotiabank confirmation.'))
        elif result.outcome == 'cancel':
            self._set_canceled(state_message=_('The payment was cancelled at the bank.'))
        else:
            self._set_error(_('Scotiabank did not approve this payment. Please try another payment method.'))
        # No account.payment creation, invoice posting, sale confirmation, custom
        # journal entries, commits, or swallowed post-processing errors here.
        # Odoo's /payment/status and native cron perform those steps.
