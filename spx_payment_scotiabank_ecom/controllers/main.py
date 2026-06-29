# -*- coding: utf-8 -*-

import logging

from werkzeug.exceptions import Forbidden

from odoo import http, _
from odoo.http import request

from ..models.payment_provider import SCOTIABANK_ECOM_CODE

_logger = logging.getLogger(__name__)


class ScotiabankEcomController(http.Controller):

    @http.route('/payment/scotiabank_ecom/handoff', type='http', auth='public', methods=['GET', 'POST'], csrf=False, website=True, sitemap=False)
    def scotiabank_handoff(self, **post):
        """Render the optional branded handoff page or iframe wrapper.

        The Odoo payment redirect form posts the already-signed Scotiabank gateway fields here.
        This controller must not change gateway fields because that would invalidate hashExtended.
        """
        if not post:
            return request.redirect('/shop')

        special = {k: v for k, v in post.items() if k.startswith('_spx_')}
        gateway_fields = {k: v for k, v in post.items() if not k.startswith('_spx_') and v not in (None, '')}

        gateway_url = special.get('_spx_gateway_url')
        if not gateway_url:
            raise Forbidden('Missing Scotiabank gateway URL.')

        values = {
            'gateway_url': gateway_url,
            'gateway_fields': sorted(gateway_fields.items()),
            'display_mode': special.get('_spx_display_mode') or 'handoff',
            'logo_url': special.get('_spx_logo_url') or '/spx_payment_scotiabank_ecom/static/src/img/spxcorp_logo_white.png',
            'header_color': special.get('_spx_header_color') or '#07101f',
            'button_color': special.get('_spx_button_color') or '#0055a4',
            'background_color': special.get('_spx_background_color') or '#f4f7fb',
            'handoff_message': special.get('_spx_handoff_message') or _('You are being securely connected to Scotiabank eCom+ to complete your payment.'),
            'loading_message': special.get('_spx_loading_message') or _('Loading secure Scotiabank eCom+ payment form…'),
            'show_powered_by': special.get('_spx_show_powered_by') == '1',
            'amount_display': special.get('_spx_amount_display') or '',
            'reference': special.get('_spx_tx_reference') or gateway_fields.get('oid') or '',
        }
        return request.render('spx_payment_scotiabank_ecom.scotiabank_handoff_page', values)

    @http.route('/payment/scotiabank_ecom/return', type='http', auth='public', methods=['GET', 'POST'], csrf=False, website=True, sitemap=False)
    def scotiabank_return(self, **post):
        """Handle customer return/callback from Scotiabank/Fiserv."""
        payment_data = dict(post)
        _logger.info('Scotiabank eCom+ return received for oid/reference %s with status %s', payment_data.get('oid'), payment_data.get('status'))
        tx_model = request.env['payment.transaction'].sudo()
        tx = tx_model._process(SCOTIABANK_ECOM_CODE, payment_data)

        # Keep Odoo's standard post-payment flow.
        # _process() validates and updates the transaction state. The sale/website
        # confirmation work happens during Odoo's own payment post-processing, so
        # trigger that natural step here instead of manually confirming any order.
        reference = payment_data.get('oid') or payment_data.get('reference') or payment_data.get('merchantTransactionId')
        if not tx:
            tx = tx_model.search([
                ('provider_code', '=', SCOTIABANK_ECOM_CODE),
                '|', ('reference', '=', reference or ''), ('scotia_oid', '=', reference or ''),
            ], limit=1)

        if tx and tx.state in ('done', 'authorized') and not tx.is_post_processed:
            try:
                tx._post_process()
            except Exception:
                _logger.exception(
                    'Scotiabank eCom+: Odoo post-processing failed for transaction %s.',
                    tx.reference,
                )

        # After post-processing, Odoo may set a landing route. Use it first because
        # this is the standard way Odoo sends website checkout customers to the
        # proper confirmation page while portal/invoice payments can use their own
        # landing page.
        if tx and tx.landing_route:
            return request.redirect(tx.landing_route)

        sale_order_id = request.session.get('sale_order_id')
        is_website_sale_payment = bool(
            sale_order_id
            and tx
            and 'sale_order_ids' in tx._fields
            and sale_order_id in tx.sale_order_ids.ids
            and tx.state in ('done', 'authorized')
        )
        if is_website_sale_payment:
            return request.redirect('/shop/payment/validate')
        return request.redirect('/payment/status')
