import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from odoo.exceptions import ValidationError
from odoo.http import Response

from .. import const
from ..controllers import main
from ..controllers.main import callback_form, ScotiabankEcomController


class TestCallbackForm(unittest.TestCase):
    def request(self, body, query=''):
        request = Request(EnvironBuilder(
            method='POST', data=body, content_type='application/x-www-form-urlencoded',
            query_string=query,
        ).get_environ())
        # Match Odoo's dispatcher: the form has already been parsed.
        dict(request.form)
        return request

    def test_already_parsed_form_is_available(self):
        self.assertEqual(callback_form(self.request('oid=order&approval_code=Y%3A123')), {'oid': 'order', 'approval_code': 'Y:123'})

    def test_query_cannot_replace_signed_body(self):
        self.assertEqual(callback_form(self.request('oid=body', 'oid=query')), {'oid': 'body'})

    def test_repeated_body_fields_rejected(self):
        with self.assertRaises(BadRequest): callback_form(self.request('oid=a&oid=b'))

    def test_wrong_content_type_rejected(self):
        request = Request(EnvironBuilder(method='POST', json={'oid': 'a'}).get_environ())
        with self.assertRaises(BadRequest): callback_form(request)

    def test_oversized_body_rejected(self):
        with self.assertRaises(RequestEntityTooLarge): callback_form(self.request('body=' + 'a' * 65536))

    def test_too_many_fields_rejected(self):
        with self.assertRaises(BadRequest): callback_form(self.request('&'.join(f'f{i}=x' for i in range(201))))

    def test_oversized_field_rejected(self):
        with self.assertRaises(BadRequest): callback_form(self.request('field=' + 'a' * 8193))

    def test_form_unicode_and_base64_preserved(self):
        self.assertEqual(callback_form(self.request('bname=Ren%C3%A9&response_hash=abc%2Bdef%3D')),
                         {'bname': 'René', 'response_hash': 'abc+def='})


class TestCallbackRouting(unittest.TestCase):
    """Controller decisions with a fake ORM; no database/accounting claims."""

    def setUp(self):
        self.env = MagicMock()
        self.env.cr.savepoint.side_effect = lambda: nullcontext()
        self.model = self.env['payment.transaction'].sudo()
        self.request = SimpleNamespace(
            env=self.env, httprequest=TestCallbackForm().request('oid=fixture'),
            render=lambda name, values, **kw: Response(template=name, qcontext=values, **kw),
        )
        self.patcher = patch.object(main, 'request', self.request)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.controller = ScotiabankEcomController()

    def test_verified_return_uses_native_status_and_never_restores_session(self):
        self.model._process.return_value = object()
        response = self.controller.scotiabank_return()
        page = response.qcontext
        self.assertEqual(page['target'], '/payment/status')
        self.assertEqual(page['screen'], 'bridge')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.model._process.assert_called_once_with(const.PROVIDER_CODE, {'source': 'return', 'payload': {'oid': 'fixture'}})

    def test_unknown_reference_shows_unverified_page(self):
        self.model._process.return_value = False
        page = self.controller.scotiabank_return().qcontext
        self.assertEqual(page['target'], const.UNVERIFIED_ROUTE)

    def test_rejected_return_shows_unverified_page(self):
        self.model._process.side_effect = ValidationError('fixture rejection')
        page = self.controller.scotiabank_return().qcontext
        self.assertEqual(page['target'], const.UNVERIFIED_ROUTE)

    def test_malformed_return_never_reaches_transaction_processing(self):
        self.request.httprequest = TestCallbackForm().request('oid=a&oid=b')
        page = self.controller.scotiabank_return().qcontext
        self.assertEqual(page['target'], const.UNVERIFIED_ROUTE)
        self.model._process.assert_not_called()

    def test_unverified_page_exposes_no_transaction(self):
        page = self.controller.scotiabank_unverified(oid='untrusted', redirect='https://untrusted.test').qcontext
        self.assertEqual(page, {'screen': 'unverified', 'show_branding': False, 'company_name': '',
                                'response_template': 'spx_paybridge_scotia.paybridge_page'})

    def test_repeated_handoff_returns_to_status_without_new_bank_form(self):
        self.request.httprequest = TestCallbackForm().request('tx_id=1&issued=123&access_token=fixture')
        tx = self.model.browse().exists()
        tx._scotia_open_handoff.return_value = None
        page = self.controller.scotiabank_checkout().qcontext
        self.assertEqual(page['target'], '/payment/status')
        self.assertNotIn('inputs', page)

    def test_invalid_handoff_does_not_expose_bank_form(self):
        self.request.httprequest = TestCallbackForm().request('tx_id=1&issued=123&access_token=invalid')
        self.model.browse().exists()._scotia_open_handoff.side_effect = ValidationError('Invalid token')
        page = self.controller.scotiabank_checkout().qcontext
        self.assertEqual(page['target'], const.UNVERIFIED_ROUTE)
        self.assertNotIn('inputs', page)
