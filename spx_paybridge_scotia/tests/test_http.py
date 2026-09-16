import unittest

from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from ..controllers.main import callback_form


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
