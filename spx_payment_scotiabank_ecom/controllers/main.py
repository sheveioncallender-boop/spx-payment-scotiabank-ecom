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

        # Website checkout needs the website sale validation route, not the generic
        # payment status route. In a second checkout attempt, Odoo may have already
        # cleared or replaced request.session['sale_order_id'] by the time Scotia
        # returns. If we then follow tx.landing_route, Odoo can fall back to /shop.
        # Restore the related website sale order into the session and let Odoo's
        # standard website_sale controller continue to /shop/confirmation.
        website_sale_order = False
        if tx and tx.state in ('done', 'authorized') and 'sale_order_ids' in tx._fields:
            website_sale_order = tx.sale_order_ids.filtered(lambda so: getattr(so, 'website_id', False))[:1]

        if website_sale_order:
            request.session['sale_order_id'] = website_sale_order.id
            request.session['sale_last_order_id'] = website_sale_order.id
            return request.redirect('/shop/payment/validate')

        # For portal quotation/invoice payment links, use Odoo's standard landing
        # route when available, otherwise use the generic payment status page.
        if tx and tx.landing_route:
            return request.redirect(tx.landing_route)
        return request.redirect('/payment/status')
