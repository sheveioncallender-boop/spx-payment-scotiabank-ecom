from odoo import _, api, fields, models

from .. import const


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    scotia_order_reference = fields.Char(
        string='Scotiabank Order Reference', related='payment_transaction_id.scotia_oid',
    )
    scotia_bank_transaction_id = fields.Char(
        string='Reported Bank Transaction ID', related='payment_transaction_id.scotia_ipg_transaction_id',
    )
    scotia_signature_verified = fields.Boolean(
        string='Bank Signature Verified', related='payment_transaction_id.scotia_response_hash_validated',
    )
    scotia_is_payment = fields.Boolean(compute='_compute_scotia_is_payment')

    @api.depends('payment_transaction_id.provider_code')
    def _compute_scotia_is_payment(self):
        for payment in self:
            payment.scotia_is_payment = payment.payment_transaction_id.provider_code == const.PROVIDER_CODE

    def action_scotia_view_transaction(self):
        self.ensure_one()
        self.check_access('read')
        tx = self.payment_transaction_id
        tx.check_access('read')
        return {
            'type': 'ir.actions.act_window', 'name': _('Payment Transaction'),
            'res_model': 'payment.transaction', 'res_id': tx.id,
            'view_mode': 'form', 'target': 'current',
        }
