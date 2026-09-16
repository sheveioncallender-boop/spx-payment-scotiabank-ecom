import logging

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

    @http.route(const.RETURN_ROUTE, type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False, max_content_length=const.MAX_CALLBACK_BYTES)
    def scotiabank_return(self, **_ignored):
        data = callback_form(request.httprequest)
        try:
            with request.env.cr.savepoint():
                request.env['payment.transaction'].sudo()._process(
                    const.PROVIDER_CODE, {'source': 'return', 'payload': data},
                )
        except ValidationError:
            _logger.warning('Scotiabank customer return rejected; awaiting a valid bank result.')
        # Odoo has already monitored the transaction when it created the payment.
        # Never grant a browser a transaction/order based on callback parameters.
        # save_session=False preserves the original Lax cookie across bank POSTs.
        return request.redirect('/payment/status', code=303)

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
