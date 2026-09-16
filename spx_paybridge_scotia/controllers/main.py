import logging
import re

from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

from .. import const

_logger = logging.getLogger(__name__)


def callback_form(http_request):
    """Read only the POST body; do not merge query-string fields into a signature."""
    if http_request.content_length and http_request.content_length > const.MAX_CALLBACK_BYTES:
        raise RequestEntityTooLarge()
    if http_request.mimetype != 'application/x-www-form-urlencoded':
        raise BadRequest('Expected a form-encoded bank response.')
    # Odoo has parsed the form before dispatch. Use the cached MultiDict,
    # preserving duplicate detection. The route caps the body BEFORE parsing.
    form = http_request.form
    if len(form) > const.MAX_CALLBACK_FIELDS:
        raise BadRequest('Too many bank response fields.')
    data = {}
    for name, values in form.lists():
        if len(values) != 1 or not name or len(name) > 128 or len(values[0]) > 8192:
            raise BadRequest('Ambiguous or oversized bank response field.')
        data[name] = values[0]
    return data


class ScotiabankEcomController(http.Controller):

    def _page(self, screen, **values):
        # Standalone QWeb page: works with invoice payments without Website.
        return request.render('spx_paybridge_scotia.paybridge_page', {
            'screen': screen, 'show_branding': False, 'company_name': '', **values,
        }, headers=[('Cache-Control', 'no-store'), ('Referrer-Policy', 'no-referrer'),
                    ('X-Frame-Options', 'SAMEORIGIN')])

    def _return_to_odoo(self, verified):
        # The only targets are local constants. Never select a session, redirect,
        # order or transaction from unauthenticated callback fields.
        return self._page('bridge', target='/payment/status' if verified else const.UNVERIFIED_ROUTE)

    @http.route(const.CHECKOUT_ROUTE, type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False, max_content_length=const.MAX_CALLBACK_BYTES)
    def scotiabank_checkout(self, **_ignored):
        try:
            data = callback_form(request.httprequest)
            if not re.fullmatch(r'[0-9]{1,12}', data.get('tx_id', '')):
                raise ValidationError('Invalid checkout identifier')
            with request.env.cr.savepoint():
                tx = request.env['payment.transaction'].sudo().browse(int(data['tx_id'])).exists()
                if not tx:
                    raise ValidationError('Unknown checkout identifier')
                parameters = tx._scotia_open_handoff(data.get('access_token'), data.get('issued'))
                if parameters is None:
                    return self._return_to_odoo(True)
                return self._page(
                    'checkout', embedded=tx.scotia_display_mode == 'embedded',
                    show_branding=tx.scotia_show_branding, company_name=tx.company_id.name,
                    reference=tx.reference, amount=tx.scotia_request_amount,
                    currency=tx.scotia_gateway_currency_alpha,
                    original_currency=tx.scotia_original_currency_alpha,
                    test_mode=tx.scotia_environment == 'test', simulation=tx.scotia_sandbox_override,
                    api_url=const.GATEWAY_URLS[tx.scotia_environment], inputs=sorted(parameters.items()),
                )
        except (ValidationError, BadRequest, RequestEntityTooLarge):
            _logger.warning('Scotiabank handoff rejected: invalid, expired or changed attempt.')
            return self._return_to_odoo(False)

    @http.route(const.UNVERIFIED_ROUTE, type='http', auth='public', methods=['GET'], save_session=False)
    def scotiabank_unverified(self, **_ignored):
        return self._page('unverified')

    @http.route(const.RETURN_ROUTE, type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False, max_content_length=const.MAX_CALLBACK_BYTES)
    def scotiabank_return(self, **_ignored):
        try:
            data = callback_form(request.httprequest)
            with request.env.cr.savepoint():
                tx = request.env['payment.transaction'].sudo()._process(
                    const.PROVIDER_CODE, {'source': 'return', 'payload': data},
                )
                if not tx:
                    _logger.warning('Scotiabank customer return rejected: unknown payment attempt.')
                verified = bool(tx)
        except (ValidationError, BadRequest, RequestEntityTooLarge):
            _logger.warning('Scotiabank customer return rejected: response could not be verified.')
            verified = False
        # Odoo has already monitored the transaction when it created the payment.
        # Never grant a browser a transaction/order based on callback parameters.
        # save_session=False preserves the original Lax cookie across bank POSTs.
        # Leave the iframe before loading the native status page, preserving the
        # original browser session and its Odoo-monitored transaction.
        return self._return_to_odoo(verified)

    @http.route(const.NOTIFY_ROUTE, type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False, max_content_length=const.MAX_CALLBACK_BYTES)
    def scotiabank_notification(self, **_ignored):
        data = callback_form(request.httprequest)
        try:
            with request.env.cr.savepoint():
                tx = request.env['payment.transaction'].sudo()._process(
                    const.PROVIDER_CODE, {'source': 'notification', 'payload': data},
                )
                if not tx:
                    return request.make_response('Unknown payment', status=404)
        except ValidationError:
            return request.make_response('Invalid bank response', status=400)
        # Transaction state is durably committed by Odoo's request transaction.
        # Native payment post-processing runs from the status page or its cron.
        return request.make_response('OK', headers=[('Content-Type', 'text/plain')], status=200)
