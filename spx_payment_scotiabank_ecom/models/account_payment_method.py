# -*- coding: utf-8 -*-

from odoo import api, models

from .payment_provider import SCOTIABANK_ECOM_CODE


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        info = super()._get_payment_method_information()
        # Odoo's account_payment app creates one electronic accounting payment method per
        # provider code. We declare Scotiabank explicitly so bank journals can create an
        # inbound payment method line for online payments/post-processing.
        info[SCOTIABANK_ECOM_CODE] = {'mode': 'electronic', 'type': ('bank', 'credit')}
        return info
