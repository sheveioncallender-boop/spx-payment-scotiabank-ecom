from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .. import const, gateway


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[(const.PROVIDER_CODE, 'Scotiabank eCom+')],
        ondelete={const.PROVIDER_CODE: 'set default'},
    )
    scotia_sandbox_store_id = fields.Char(string='Test Store ID', copy=False)
    scotia_sandbox_shared_secret = fields.Char(
        string='Test Shared Secret', copy=False, groups='base.group_system',
    )
    scotia_live_store_id = fields.Char(string='Live Store ID', copy=False)
    scotia_live_shared_secret = fields.Char(
        string='Live Shared Secret', copy=False, groups='base.group_system',
    )
    scotia_sandbox_previous_secret = fields.Char(
        string='Previous Test Secret', copy=False, groups='base.group_system',
        help='Only for a credential rotation: verifies responses from outstanding older attempts.',
    )
    scotia_live_previous_secret = fields.Char(
        string='Previous Live Secret', copy=False, groups='base.group_system',
        help='Only for a credential rotation: verifies responses from outstanding older attempts.',
    )
    scotia_notification_url = fields.Char(
        string='Bank Notification URL', compute='_compute_scotia_urls',
    )
    scotia_return_url = fields.Char(string='Customer Return URL', compute='_compute_scotia_urls')

    def _compute_scotia_urls(self):
        for provider in self:
            base = provider.get_base_url().rstrip('/')
            provider.scotia_notification_url = base + const.NOTIFY_ROUTE
            provider.scotia_return_url = base + const.RETURN_ROUTE

    def _get_default_payment_method_codes(self):
        if self.code == const.PROVIDER_CODE:
            return {'card'}
        return super()._get_default_payment_method_codes()

    def _get_supported_currencies(self):
        currencies = super()._get_supported_currencies()
        if self.code == const.PROVIDER_CODE:
            currencies = currencies.filtered(lambda c: c.name in const.CURRENCY_CODES)
        return currencies

    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == const.PROVIDER_CODE).update({
            'support_express_checkout': False,
            'support_manual_capture': False,
            'support_refund': 'none',
            'support_tokenization': False,
        })

    def _get_redirect_form_view(self, is_validation=False):
        if self.code == const.PROVIDER_CODE:
            return self.env.ref('spx_paybridge_scotia.paybridge_redirect_form')
        return super()._get_redirect_form_view(is_validation=is_validation)

    @api.constrains('code', 'state', 'scotia_sandbox_store_id', 'scotia_sandbox_shared_secret',
                    'scotia_live_store_id', 'scotia_live_shared_secret')
    def _check_scotia_credentials(self):
        for provider in self.filtered(lambda p: p.code == const.PROVIDER_CODE and p.state != 'disabled'):
            environment = 'test' if provider.state == 'test' else 'live'
            store, secret = provider.sudo()._scotia_credentials(environment)
            if not store or not secret:
                raise ValidationError(_(
                    'Enter the Scotiabank %(mode)s Store ID and Shared Secret before activating this mode.',
                    mode=environment,
                ))
            if any(char.isspace() for char in store) or '|' in store:
                raise ValidationError(_('The Scotiabank Store ID must not contain spaces or a pipe character.'))

    def _scotia_credentials(self, environment):
        self.ensure_one()
        if environment == 'test':
            return self.scotia_sandbox_store_id or '', self.scotia_sandbox_shared_secret or ''
        if environment == 'live':
            return self.scotia_live_store_id or '', self.scotia_live_shared_secret or ''
        raise ValidationError(_('Unknown Scotiabank environment.'))

    def _scotia_response_secrets(self, environment):
        self.ensure_one()
        # Select from the saved attempt environment, not the provider's current
        # state: a test response must never become a live payment after a switch.
        _store, current = self._scotia_credentials(environment)
        previous = (self.scotia_sandbox_previous_secret if environment == 'test'
                    else self.scotia_live_previous_secret)
        return [current, previous]

    def _scotia_check_configuration(self):
        self.ensure_one()
        if self.code != const.PROVIDER_CODE or self.state not in ('test', 'enabled'):
            raise ValidationError(_('Choose Test Mode or Enabled on the Scotiabank provider first.'))
        self._check_scotia_credentials()
        try:
            base_url = gateway.public_base_url(self.get_base_url())
        except ValueError as exc:
            raise ValidationError(_(
                'Set the public Odoo URL to HTTPS on port 443, without a path or query string.'
            )) from exc
        if not self.journal_id or self.journal_id.type != 'bank':
            raise ValidationError(_('Select the standard bank Payment Journal on the Configuration tab.'))
        if self.journal_id.company_id != self.company_id:
            raise ValidationError(_('The payment journal must belong to the provider company.'))
        method_line = self.journal_id.inbound_payment_method_line_ids.filtered(
            lambda line: line.payment_provider_id == self
        )
        if len(method_line) != 1:
            raise ValidationError(_(
                'The selected journal needs one Scotiabank incoming payment method. '
                'Save the standard Payment Journal field to let Odoo configure it.'
            ))
        if not method_line.payment_account_id:
            raise ValidationError(_(
                'Set an Outstanding Receipts account on the journal\'s Scotiabank incoming '
                'payment method so Odoo can create the normal payment journal entry.'
            ))
        if not self.available_currency_ids:
            raise ValidationError(_(
                'Select the currencies enabled on this Scotiabank Store ID in Configuration > Currencies.'
            ))
        return base_url

    def action_scotia_check_configuration(self):
        self._scotia_check_configuration()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Scotiabank configuration'), 'type': 'success', 'sticky': True,
                'message': _(
                    'Local configuration is ready. This check does not contact the bank or verify '
                    'credentials. Complete a test payment to verify bank acceptance and accounting.'
                ),
            },
        }

    def _get_removal_values(self):
        values = super()._get_removal_values()
        values.update({key: False for key in (
            'scotia_sandbox_store_id', 'scotia_sandbox_shared_secret',
            'scotia_live_store_id', 'scotia_live_shared_secret',
            'scotia_sandbox_previous_secret', 'scotia_live_previous_secret',
        )})
        return values
