from . import models
from . import controllers

import odoo.addons.payment as payment


def post_init_hook(env):
    payment.setup_provider(env, 'spx_paybridge_scotia')


def uninstall_hook(env):
    payment.reset_payment_provider(env, 'spx_paybridge_scotia')
