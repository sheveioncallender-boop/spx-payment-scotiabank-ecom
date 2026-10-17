from odoo import api, fields, models
from odoo.addons.spx_paybridge_scotia import const


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    spx_scotia_online = fields.Boolean(compute='_compute_spx_scotia_online')

    @api.depends('is_online_payment', 'online_payment_provider_ids')
    def _compute_spx_scotia_online(self):
        for method in self:
            method.spx_scotia_online = bool(
                method.is_online_payment
                and const.PROVIDER_CODE in method._get_online_payment_providers().mapped('code')
            )

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ['spx_scotia_online']
