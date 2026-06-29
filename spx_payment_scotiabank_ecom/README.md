# SPX Scotiabank eCom+ Payment Gateway for Odoo

Version: **1.0.0**  
Author: **Sheveion Callender / SPXCORP Limited**

This Odoo module adds **Scotiabank eCom+** as a hosted payment provider using the Fiserv/IPG Connect hosted payment page flow.

## Supported flows

- Odoo website checkout payment option
- Sale order / invoice portal payment links through Odoo's standard `payment.transaction` flow
- Scotiabank/Fiserv hosted page redirection
- SPXCORP branded handoff page
- Optional iframe wrapper

## Not included yet

Refunds, captures, voids, tokenization, and recurring payments are not included in this first version. Those require separate Fiserv REST API credentials.

## GitHub / Cloudpepper structure

Upload the folder exactly like this:

```text
spx-odoo-addons/
└── spx_payment_scotiabank_ecom/
    ├── __init__.py
    ├── __manifest__.py
    ├── controllers/
    ├── models/
    ├── views/
    ├── data/
    ├── static/
    └── README.md
```

## Install

1. Add this folder to your GitHub Odoo addons repository.
2. Pull/update the repo in Cloudpepper.
3. Restart Odoo.
4. Go to **Apps** and click **Update Apps List**.
5. Search for **SPX Scotiabank eCom+ Payment Gateway**.
6. Install.

## Configure

Go to one of these paths:

- **Accounting > Configuration > Payment Providers**
- **Website > Configuration > Payment Providers**
- **Sales > Configuration > Payment Providers**

Open **Scotiabank eCom+** and configure:

- Store ID / Store Name
- Shared Secret
- Test or Enabled state
- Sandbox currency override if needed, e.g. `840` for USD sandbox testing
- Payment Display Mode
- Branding options

## Important currency note

If Odoo is set to **TTD**, the gateway sends `780` by default.

If the sandbox Store ID only accepts USD, set:

```text
Sandbox Currency Code Override = 840
```

This does **not** convert the amount. It only changes the numeric currency code sent to Scotiabank/Fiserv.

## Test card

Use Scotia/Fiserv-provided sandbox cards. One known Fiserv sandbox test card that worked in WooCommerce testing was:

```text
Card: 4005520000000129
Expiry: 10/30
CVV: 002
```

Use the card list Scotia provides for your specific sandbox Store ID when available.


## v1.0.5
- Added separate sandbox and live credentials.
- Removed hard required fields from disabled provider settings.
- Active mode now selects the correct Store ID and Shared Secret automatically.


## v1.0.7
- Fixed recursion when enabling provider caused by automatic Card payment method linking.
- Clarified Scotiabank eCom+ Setup tab text.


## v1.0.7
- Fixed Scotiabank/Fiserv response hash validation when the return payload omits `storename`.
- Normalizes Base64 response hashes where `+` is received as a space.
- Stores the Store ID used for each transaction so the response hash can be validated against the exact payment attempt.


## v1.0.9
- Redirect successful website checkout payments through Odoo's standard /shop/payment/validate route so customers land on the normal /shop/confirmation page.
- Ensures the accounting payment method line before confirming approved Scotiabank transactions.


## v1.0.11
- Fixed repeat website checkout return routing by restoring the related website sale order in session before calling Odoo standard /shop/payment/validate.
