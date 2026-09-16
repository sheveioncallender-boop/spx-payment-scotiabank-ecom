"""Execute the actual Odoo 19 standalone QWeb compiler, without a database."""
import unittest
from pathlib import Path

from lxml import etree, html
from odoo.addons.base.models.ir_qweb import render


TEMPLATES = Path(__file__).resolve().parents[1] / 'views/payment_scotiabank_templates.xml'


def render_page(**changes):
    def load(name):
        tree = etree.parse(str(TEMPLATES)).find("template[@id='paybridge_page']")
        tree.tag = 't'
        tree.attrib.clear()
        return tree, name
    values = {
        'screen': 'checkout', 'show_branding': True, 'company_name': 'Fixture Merchant',
        'embedded': False, 'reference': 'TEST-600', 'amount': '600.00',
        'currency': 'USD', 'original_currency': 'TTD', 'test_mode': True, 'simulation': True,
        'api_url': '/fake-bank', 'inputs': [('oid', 'TEST-600')], **changes,
    }
    return str(render('paybridge_page', values, load))


class TestHandoffTemplates(unittest.TestCase):
    def test_branded_handoff_renders_original_identity_and_simulation(self):
        document = html.fromstring(render_page())
        self.assertEqual(document.xpath('//img/@alt'), ['SPXCORP LTD'])
        self.assertIn('Sandbox simulation', document.text_content())
        self.assertIn('600.00 TTD', ' '.join(document.text_content().split()))
        self.assertEqual(document.xpath('//form/@target'), ['_top'])

    def test_embed_uses_named_bank_frame(self):
        document = html.fromstring(render_page(embedded=True))
        self.assertEqual(document.xpath('//form/@target'), document.xpath('//iframe/@name'))
        self.assertEqual(document.xpath('//iframe/@referrerpolicy'), ['no-referrer'])

    def test_live_page_never_displays_test_override(self):
        document = html.fromstring(render_page(test_mode=False, simulation=False, currency='TTD'))
        self.assertNotIn('USD', document.text_content())
        self.assertNotIn('Sandbox simulation', document.text_content())

    def test_brand_toggle_and_untrusted_text_are_escaped(self):
        document = html.fromstring(render_page(show_branding=False, reference='<script>bad()</script>'))
        self.assertFalse(document.xpath('//img'))
        self.assertIn('Fixture Merchant', document.text_content())
        self.assertFalse(document.xpath('//script[not(@src)]'))
        self.assertIn('<script>bad()</script>', document.text_content())

    def test_return_bridge_has_only_local_status_link(self):
        document = html.fromstring(render_page(screen='bridge', target='/payment/status'))
        self.assertEqual(document.xpath('//a[@id="spx-return"]/@href'), ['/payment/status'])
        self.assertFalse(document.xpath('//form'))

    def test_unverified_page_does_not_include_payment_data(self):
        document = html.fromstring(render_page(screen='unverified'))
        self.assertNotIn('TEST-600', document.text_content())
        self.assertNotIn('600.00', document.text_content())
        self.assertFalse(document.xpath('//form'))
