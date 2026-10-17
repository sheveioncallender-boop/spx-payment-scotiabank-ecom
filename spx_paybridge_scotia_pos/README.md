# Native POS online-payment completion

Optional, automatically installed integration for Odoo 19 when both
`spx_paybridge_scotia` and Odoo's `pos_online_payment` are installed.
It does not install POS into a website-only database.

## What it repairs

- A confirmed online payment can leave the POS waiting for another Validate click.
- The temporary QR payment line can survive beside the persisted payment, making
  the receipt show a duplicate payment and negative change.
- The online completion path can skip the normal paid-order loyalty hook.

The adapter monitors only online payment methods offering Scotia. After the
cashier begins native validation, it checks the native authenticated status RPC
while POS is open. It reloads the paid order using `read_pos_orders`, removes only
unsaved online payment placeholders from the browser, invokes
`postSyncAllOrders`, then uses native receipt completion for the selected ticket.
A cashier working on another ticket keeps that screen.

Odoo remains responsible for signed payment confirmation, POS payment creation,
accounting, invoices, reconciliation, loyalty rules, reward redemption and
`confirm_coupon_programs`. No payment, journal entry, invoice, loyalty balance or
server payment line is created/deleted directly by this module. Odoo core files
are not changed. Other payment providers and ordinary cash/card sales retain
native handling. Concurrent completion events share one operation; native
loyalty history also provides its existing duplicate-confirmation protection.

## Deploy an existing database

1. Pull/rebuild `rebuild-odoo19-enterprise` in Cloudpepper.
2. Update the Odoo Apps list so the new companion module is discovered.
3. Upgrade **Spxcorp PayBridge - Scotiabank eCom+** to **19.0.1.1.2**.
4. Verify **Spxcorp PayBridge - Native POS Completion** is installed. It is
   auto-installable when its dependencies are present. If the deployment's app
   update has not run dependency auto-install, install this companion once.
5. Reload the POS browser to load the updated assets and payment-method flag.
   Keep the provider in Test Mode for acceptance testing.

Do not uninstall/reinstall PayBridge and do not alter existing payment records.

## Regression tests

```sh
node --test spx_paybridge_scotia_pos/tests/test_online_payment.mjs
ODOO_ROOT=/path/to/odoo19 node --test spx_paybridge_scotia_pos/tests/test_online_payment.mjs
```

The second command also executes the actual native online validation extension
and demonstrates the unpatched duplicate/loyalty-hook regression. The tests
exercise orchestration with a simulated POS data service, not a running Odoo
browser or a live bank.

After deployment, repeat the sandbox checkout while staying on the payment
screen and while switching to another ticket. Verify one persisted POS payment,
one receipt line, zero false change, one native loyalty history award, the
unchanged native accounting entry, and no award for a failed or unpaid bill.

The status fallback needs an open POS browser. It is not a server-only loyalty
engine and does not add payment to the mobile app. Settlement reconciliation,
closed-browser payment recovery and the mobile payment flow require their own
acceptance tests before production release.
