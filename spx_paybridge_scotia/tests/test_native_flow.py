"""Run on an Odoo 19 Enterprise test database; never makes external bank calls."""
import base64
import hashlib
import hmac
import time
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.addons.account_payment.tests.common import AccountPaymentCommon

from .. import const, gateway


@tagged('post_install', '-at_install')
class TestPayBridgeNativeFlow(AccountPaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('web.base.url', 'https://odoo.example.test')
        cls.env['payment.provider']._setup_payment_method(const.PROVIDER_CODE)
        cls.payment_method = cls.env.ref('payment.payment_method_card')
        cls.payment_method_id = cls.payment_method.id
        cls.payment_method.active = True
        cls.provider = cls.env['payment.provider'].create({
            'name': 'PayBridge Test', 'code': const.PROVIDER_CODE,
            'company_id': cls.env.company.id,
            'scotia_sandbox_store_id': 'fixture-store',
            'scotia_sandbox_shared_secret': 'fixture-secret',
            'scotia_live_store_id': 'fixture-live-store',
            'scotia_live_shared_secret': 'fixture-live-secret',
            'state': 'test', 'journal_id': cls.company_data['default_journal_bank'].id,
            'payment_method_ids': [Command.set(cls.payment_method.ids)],
            'available_currency_ids': [Command.set(cls.currency.ids)],
        })
        line = cls.provider.journal_id.inbound_payment_method_line_ids.filtered(lambda item: item.payment_provider_id == cls.provider)
        line.payment_account_id = cls.inbound_payment_method_line.payment_account_id

    def attempt(self, **values):
        tx = self._create_transaction('redirect', **values)
        tx._get_specific_rendering_values({})
        return tx

    def bank_response(self, tx, source='notification', approval='Y:123456'):
        data = {
            'oid': tx.scotia_oid, 'chargetotal': tx.scotia_request_amount,
            'currency': tx.scotia_gateway_currency_numeric,
            'txndatetime': tx.scotia_request_datetime,
            'approval_code': approval, 'status': 'APPROVED',
            'ipgTransactionId': 'fixture-' + str(tx.id), 'txntype': 'sale',
        }
        parts = [data['chargetotal'], data['currency'], data['txndatetime'], tx.scotia_gateway_store_id]
        parts = parts + [approval] if source == 'notification' else [approval] + parts
        data['notification_hash' if source == 'notification' else 'response_hash'] = base64.b64encode(
            hmac.new(b'fixture-secret', '|'.join(parts).encode(), hashlib.sha256).digest()
        ).decode()
        return {'source': source, 'payload': data}

    def test_payment_is_created_by_native_post_processing(self):
        invoice = self.init_invoice('out_invoice', self.partner, amounts=[self.amount], taxes=[], currency=self.currency)
        invoice.action_post()
        tx = self.attempt(invoice_ids=[Command.set(invoice.ids)])
        data = self.bank_response(tx)
        tx._process(const.PROVIDER_CODE, data)
        self.assertEqual(tx.state, 'done')
        self.assertFalse(tx.payment_id)
        tx._post_process()
        self.assertTrue(tx.payment_id)
        self.assertEqual(tx.payment_id.payment_transaction_id, tx)
        self.assertEqual(tx.payment_id.journal_id, self.provider.journal_id)
        self.assertEqual(tx.payment_id.move_id.state, 'posted')
        self.assertEqual(tx.payment_id.amount, tx.amount)
        self.assertEqual(tx.payment_id.currency_id, tx.currency_id)
        self.assertEqual(invoice.amount_residual, 0)
        self.assertIn(invoice.payment_state, ('in_payment', 'paid'))
        self.assertIn(tx.scotia_oid, tx.payment_id.memo)
        payment = tx.payment_id
        tx._process(const.PROVIDER_CODE, data)
        tx._process(const.PROVIDER_CODE, self.bank_response(tx, source='return'))
        tx._post_process()
        self.assertEqual(tx.payment_id, payment)
        self.assertEqual(self.env['account.payment'].search_count([('payment_transaction_id', '=', tx.id)]), 1)

    def test_invalid_notification_never_changes_state(self):
        tx = self.attempt()
        data = self.bank_response(tx); data['payload']['notification_hash'] = 'invalid'
        with self.assertRaises(ValidationError): tx._process(const.PROVIDER_CODE, data)
        self.assertEqual(tx.state, 'draft')
        self.assertFalse(tx.payment_id)

    def test_same_amount_order_replay_rejected(self):
        first = self.attempt(reference='first-order')
        second = self.attempt(reference='second-order')
        self.assertNotEqual(first.scotia_request_datetime, second.scotia_request_datetime)
        data = self.bank_response(first)
        data['payload'].update(oid=second.scotia_oid, txndatetime=second.scotia_request_datetime)
        with self.assertRaises(ValidationError): second._process(const.PROVIDER_CODE, data)
        self.assertEqual(second.state, 'draft')

    def test_signed_decline_ignores_unsigned_approved_status(self):
        tx = self.attempt()
        tx._process(const.PROVIDER_CODE, self.bank_response(tx, approval='N:DECLINED'))
        self.assertEqual(tx.state, 'error')
        tx._post_process()
        self.assertFalse(tx.payment_id)

    def test_late_failure_does_not_downgrade_success(self):
        tx = self.attempt()
        tx._process(const.PROVIDER_CODE, self.bank_response(tx))
        original = tx.provider_reference
        tx._process(const.PROVIDER_CODE, self.bank_response(tx, approval='N:DECLINED'))
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, original)

    def test_mode_switch_does_not_change_inflight_secret(self):
        tx = self.attempt()
        self.provider.state = 'enabled'
        tx._process(const.PROVIDER_CODE, self.bank_response(tx))
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.scotia_environment, 'test')

    def test_missing_phone_does_not_break_redirect(self):
        self.partner.phone = False
        tx = self._create_transaction('redirect')
        values = tx._get_specific_rendering_values({})
        self.assertEqual(values['api_url'], const.GATEWAY_URLS['test'])
        self.assertNotIn('phone', dict(values['inputs']))

    def test_sandbox_keeps_native_currency_and_validates_bank_usd(self):
        tx = self.attempt()
        self.assertNotEqual(self.currency.name, 'USD')
        self.assertEqual(tx.currency_id, self.currency)
        self.assertEqual(tx.scotia_original_currency_alpha, self.currency.name)
        self.assertEqual(tx.scotia_gateway_currency_numeric, '840')
        self.assertTrue(tx.scotia_sandbox_override)
        self.assertFalse(tx.is_live)
        tx._process(const.PROVIDER_CODE, self.bank_response(tx))
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.currency_id, self.currency)

    def test_live_always_sends_original_currency(self):
        self.provider.state = 'enabled'
        tx = self.attempt()
        self.assertTrue(tx.is_live)
        self.assertFalse(tx.scotia_sandbox_override)
        self.assertEqual(tx.scotia_gateway_currency_alpha, self.currency.name)

    def test_disabling_override_rejects_non_usd_sandbox(self):
        self.provider.scotia_sandbox_usd_override = False
        with self.assertRaises(ValidationError): self.attempt()

    def test_currency_settings_cannot_rewrite_existing_attempt(self):
        self.provider.scotia_display_mode = 'branded'
        tx = self.attempt()
        saved = (tx.scotia_oid, tx.scotia_request_datetime, tx.scotia_gateway_currency_numeric)
        self.provider.scotia_sandbox_usd_override = False
        with self.assertRaises(ValidationError): tx._scotia_prepare_attempt()
        self.assertEqual(saved, (tx.scotia_oid, tx.scotia_request_datetime, tx.scotia_gateway_currency_numeric))

    def test_direct_form_cannot_be_issued_twice(self):
        tx = self.attempt()
        with self.assertRaises(ValidationError): tx._get_specific_rendering_values({})

    def test_handoff_opens_once_with_unchanged_reference(self):
        self.provider.scotia_display_mode = 'embedded'
        tx = self._create_transaction('redirect')
        rendered = tx._get_specific_rendering_values({})
        self.assertEqual(rendered['api_url'], const.CHECKOUT_ROUTE)
        data = dict(rendered['inputs'])
        self.assertNotIn('hashExtended', data)
        parameters = tx._scotia_open_handoff(data['access_token'], data['issued'])
        self.assertEqual(parameters['parentUri'], 'https://odoo.example.test' + const.CHECKOUT_ROUTE)
        self.assertEqual(parameters['language'], 'en_GB')
        self.assertEqual(parameters['oid'], tx.scotia_oid)
        self.assertEqual(parameters['hashExtended'], gateway.request_hash(parameters, 'fixture-secret'))
        self.assertIsNone(tx._scotia_open_handoff(data['access_token'], data['issued']))
        self.assertEqual(tx.state, 'draft')
        self.assertFalse(tx.payment_id)

    def test_invalid_or_cross_transaction_handoff_token_cannot_open_bank(self):
        self.provider.scotia_display_mode = 'branded'
        first, second = self.attempt(reference='one'), self.attempt(reference='two')
        issued = str(int(time.time()))
        for token in [None, 'invalid', 'é' * 64, second._scotia_checkout_token(issued)]:
            with self.subTest(token=token), self.assertRaises(ValidationError):
                first._scotia_open_handoff(token, issued)
        self.assertFalse(first.scotia_handoff_started)

    def test_expired_handoff_token_cannot_open_bank(self):
        self.provider.scotia_display_mode = 'branded'
        tx = self.attempt()
        issued = str(int(time.time()) - const.CHECKOUT_TOKEN_TTL - 1)
        with self.assertRaises(ValidationError):
            tx._scotia_open_handoff(tx._scotia_checkout_token(issued), issued)
        self.assertFalse(tx.scotia_handoff_started)

    def test_only_embedded_mode_sends_parent_uri(self):
        self.provider.scotia_display_mode = 'branded'
        tx = self.attempt()
        self.assertNotIn('parentUri', tx._scotia_bank_parameters())

    def test_sandbox_response_cannot_authorize_live_transaction(self):
        tx = self.attempt()
        tx.is_live = True
        with self.assertRaises(ValidationError): tx._process(const.PROVIDER_CODE, self.bank_response(tx))
        self.assertEqual(tx.state, 'draft')
        self.assertFalse(tx.payment_id)

    def test_native_post_processing_error_rolls_back_for_retry(self):
        tx = self.attempt()
        tx._process(const.PROVIDER_CODE, self.bank_response(tx))
        with patch.object(type(tx), '_create_payment', side_effect=ValidationError('fixture accounting issue')):
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                tx._post_process()
        tx.invalidate_recordset()
        self.assertFalse(tx.is_post_processed)
        self.assertFalse(tx.payment_id)
        tx._post_process()
        self.assertTrue(tx.payment_id)

    def test_provider_copy_does_not_copy_credentials(self):
        provider_copy = self.provider.copy({'state': 'disabled'})
        self.assertFalse(provider_copy.scotia_sandbox_shared_secret)
        self.assertFalse(provider_copy.scotia_live_shared_secret)

    def test_unsupported_features_are_not_advertised(self):
        self.assertEqual(self.provider.support_refund, 'none')
        self.assertFalse(self.provider.support_manual_capture)
        self.assertFalse(self.provider.support_tokenization)
