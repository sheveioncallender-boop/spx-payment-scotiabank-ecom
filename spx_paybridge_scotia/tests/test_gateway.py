import base64
import hashlib
import hmac
import unittest
from dataclasses import replace

from .. import gateway


class TestGatewayProtocol(unittest.TestCase):
    secret = 'local-test-secret-not-a-credential'

    def setUp(self):
        self.expected = gateway.ExpectedPayment(
            oid='INV-2026-0042-aabb', amount='100.00', currency='780',
            txndatetime='2026:09:16-15:30:01', store_id='test-store',
        )

    def signed(self, source='return', **changes):
        values = {
            'oid': self.expected.oid, 'chargetotal': '100.00', 'currency': '780',
            'txndatetime': self.expected.txndatetime, 'txntype': 'sale',
            'approval_code': 'Y:123456', 'status': 'APPROVED',
            'ipgTransactionId': '123456789', 'cardnumber': '(VISA) ... 1234',
        }
        values.update(changes)
        # Independent construction of the formulas printed in the bank manual.
        components = [values['chargetotal'], values['currency'], values['txndatetime'], 'test-store']
        components = components + [values['approval_code']] if source == 'notification' else [values['approval_code']] + components
        key = 'notification_hash' if source == 'notification' else 'response_hash'
        values[key] = base64.b64encode(hmac.new(
            self.secret.encode(), '|'.join(components).encode(), hashlib.sha256,
        ).digest()).decode()
        return values

    def verify(self, data, source='return', expected=None, secrets=None):
        return gateway.verify_response(data, secrets or [self.secret], expected or self.expected, source)

    def test_official_fiserv_request_vector(self):
        values = {
            'chargetotal': '13.00', 'checkoutoption': 'combinedpage', 'currency': '978',
            'hash_algorithm': 'HMACSHA256', 'paymentMethod': 'M',
            'responseFailURL': 'https://localhost:8643/webshop/response_failure.jsp',
            'responseSuccessURL': 'https://localhost:8643/webshop/response_success.jsp',
            'storename': '10123456789', 'timezone': 'Europe/Berlin',
            'transactionNotificationURL': 'https://localhost:8643/webshop/transactionNotification',
            'txndatetime': '2021:09:06-16:43:04', 'txntype': 'sale',
        }
        self.assertEqual(gateway.request_hash(values, 'sharedsecret'), 'EapafBqqOF6N/kch8USkHPGh+fwSko24h6FpQnQHfQ8=')

    def test_request_ignores_empty_and_secret_fields(self):
        values = {'oid': 'order', 'chargetotal': '10.00'}
        digest = gateway.request_hash(values, self.secret)
        self.assertEqual(digest, gateway.request_hash(dict(values, sharedsecret='never-send', hashExtended='old', phone=''), self.secret))

    def test_return_approval(self):
        result = self.verify(self.signed())
        self.assertEqual((result.outcome, result.card_last4), ('done', '1234'))

    def test_server_notification(self):
        self.assertEqual(self.verify(self.signed('notification'), 'notification').outcome, 'done')

    def test_notification_needs_its_own_formula(self):
        data = self.signed()
        data['notification_hash'] = data['response_hash']
        with self.assertRaises(gateway.InvalidResponse): self.verify(data, 'notification')

    def test_forged_status_cannot_approve_signed_decline(self):
        data = self.signed(approval_code='N:DECLINED', status='DECLINED')
        data.update(status='APPROVED', processor_response_code='00')
        self.assertEqual(self.verify(data).outcome, 'error')

    def test_signed_waiting_is_not_paid(self):
        self.assertEqual(self.verify(self.signed(approval_code='?:WAIT', status='APPROVED')).outcome, 'pending')

    def test_approval_tampering_rejected(self):
        data = self.signed(approval_code='N:DECLINED')
        data['approval_code'] = 'Y:123456'
        with self.assertRaises(gateway.InvalidResponse): self.verify(data)

    def test_cross_order_replay_rejected_by_stored_timestamp(self):
        data = self.signed()
        expected_b = replace(self.expected, oid='OTHER-ORDER', txndatetime='2026:09:16-15:30:02')
        data.update(oid=expected_b.oid, txndatetime=expected_b.txndatetime)
        with self.assertRaises(gateway.InvalidResponse): self.verify(data, expected=expected_b)

    def test_wrong_oid_rejected(self):
        data = self.signed(); data['oid'] = 'OTHER'
        with self.assertRaises(gateway.InvalidResponse): self.verify(data)

    def test_changed_timestamp_rejected(self):
        data = self.signed(); data['txndatetime'] = '2020:01:01-00:00:00'
        with self.assertRaises(gateway.InvalidResponse): self.verify(data)

    def test_missing_echoed_store_and_timestamp_use_originals(self):
        data = self.signed(); data.pop('txndatetime')
        self.assertEqual(self.verify(data).outcome, 'done')

    def test_currency_mismatch_rejected_even_if_signed(self):
        with self.assertRaises(gateway.InvalidResponse): self.verify(self.signed(currency='840'))

    def test_amount_mismatch_rejected_even_if_signed(self):
        with self.assertRaises(gateway.InvalidResponse): self.verify(self.signed(chargetotal='99.99'))

    def test_wrong_merchant_store_rejected(self):
        data = self.signed(); data['storename'] = 'another-store'
        with self.assertRaises(gateway.InvalidResponse): self.verify(data)

    def test_missing_signature_never_accepted(self):
        data = self.signed(); data.pop('response_hash')
        with self.assertRaises(gateway.InvalidResponse): self.verify(data)

    def test_wrong_secret_never_accepted(self):
        with self.assertRaises(gateway.InvalidResponse): self.verify(self.signed(), secrets=['wrong'])

    def test_previous_secret_during_rotation(self):
        self.assertEqual(self.verify(self.signed(), secrets=['replacement', self.secret]).outcome, 'done')

    def test_missing_amount_rejected(self):
        data = self.signed(); data.pop('chargetotal')
        with self.assertRaises(gateway.InvalidResponse): self.verify(data)

    def test_nonfinite_and_fractional_amounts_rejected(self):
        for amount in ['NaN', 'Infinity', '-1', '0', '1.001', '', None]:
            with self.subTest(amount=amount), self.assertRaises(gateway.InvalidResponse): gateway.amount_string(amount)

    def test_partial_approval_held_for_review(self):
        with self.assertRaises(gateway.InvalidResponse): self.verify(self.signed(partiallyApprovedAmount='50.00'))

    def test_full_card_number_reduced_to_four_digits(self):
        result = self.verify(self.signed(cardnumber='4111111111111111'))
        self.assertEqual(result.card_last4, '1111')
        self.assertNotIn('4111111111111111', repr(result))

    def test_reported_transaction_id_is_not_payment_evidence(self):
        data = self.signed(approval_code='N:DECLINED', ipgTransactionId='attacker-reported-id')
        self.assertEqual(self.verify(data).outcome, 'error')

    def test_bad_base64_rejected(self):
        data = self.signed(); data['response_hash'] = '%%%'
        with self.assertRaises(gateway.InvalidResponse): self.verify(data)

    def test_https_origin_required(self):
        self.assertEqual(gateway.public_base_url('https://odoo.example.test/'), 'https://odoo.example.test')
        for url in ['http://odoo.test', 'https://odoo.test:8069', 'https://odoo.test/path', 'https://user:secret@odoo.test', 'javascript:alert(1)']:
            with self.subTest(url=url), self.assertRaises(ValueError): gateway.public_base_url(url)
