# Spxcorp PayBridge - Scotiabank eCom+

A fresh payment-provider module for **Odoo 19 Enterprise** by **Spxcorp Limited**.

- App: **Spxcorp PayBridge - Scotiabank eCom+**
- Technical module and provider code: `spx_paybridge_scotia`
- Version: `19.0.1.1.1`
- Repository: `sheveioncallender-boop/spx-payment-scotiabank-ecom`
- Deployment: new Odoo 19 Enterprise instance on Cloudpepper

This is a new application identity. It does not upgrade or migrate the earlier
`spx_payment_scotiabank_ecom` app. Its existing repository folder is left unchanged
for existing deployments; the new application has its own folder and provider code.

## What PayBridge does

Customers pay on Scotiabank's hosted card page using the existing Store ID and
Shared Secret. PayBridge verifies the bank's standard response or notification
signature, then updates Odoo's normal `payment.transaction` record. It requires
no optional account feature to be enabled by the bank.

Odoo performs the remaining work through its native payment post-processing:

| Odoo record/workflow | Behaviour |
| --- | --- |
| Website checkout | Uses the standard payment selection, status page and order confirmation when Website/eCommerce is installed. |
| Sales quotations and payment links | Uses native portal payments when Sales is installed. |
| Customer invoices | Uses the normal invoice payment link. |
| Customer payments | Odoo creates the standard incoming payment in the provider's selected bank journal. |
| Journal entries | Odoo posts its standard payment entry using the journal's incoming payment method and Outstanding Receipts account. |
| Receivable matching | Odoo reconciles the linked invoice receivable against the customer payment. |
| Bank reconciliation | Existing Odoo statement/reconciliation tools handle the later bank deposit, settlement batches and fees. |

An invoice can correctly remain **In Payment** until bank reconciliation, according
to the journal and outstanding-account configuration. PayBridge does not force
Paid, manufacture a bank statement, replace the accounting engine or record
settlement fees automatically.

## Install on Cloudpepper

1. Use a fresh **Odoo 19 Enterprise** instance with Enterprise Accounting available.
2. Select branch **rebuild-odoo19-enterprise** in this repository.
3. The addon is the single folder `spx_paybridge_scotia` at the repository root.
   Its manifest is `spx_paybridge_scotia/__manifest__.py`. That whole folder can
   also be copied to another addons repository without a separate support folder.
4. Pull/redeploy that branch in Cloudpepper and restart the Odoo service.
5. Update the Apps list. Remove the **Apps** search filter if it hides payment providers.
6. Search for **Spxcorp PayBridge** and install it.
7. Open **Accounting > Configuration > Payment Providers > Scotiabank eCom+**.

The repository root contains `spx_paybridge_scotia/__manifest__.py`, matching the
usual Cloudpepper external-addon layout. Do not rename that folder. Install only
the new PayBridge application on the fresh instance; the existing application is
not migrated or reconfigured.

The manifest depends on `payment`, `account_payment`, and Enterprise
`account_accountant`. Sales and Website/eCommerce are optional existing apps;
PayBridge does not force their installation just to accept invoice payments.

### Update an installed PayBridge

Pull/redeploy **rebuild-odoo19-enterprise** in Cloudpepper, then upgrade
**Spxcorp PayBridge** in Apps. Restart Odoo as part of the normal module upgrade.
Updating the Apps list alone is insufficient: this version adds database fields.
Verify installed version **19.0.1.1.1**. Existing credentials and completed
transactions are retained. Start a new sandbox attempt from the original Odoo
document; old attempts keep the currency and request time they originally used.

If the previous upgrade failed with **column payment_provider.scotia_sandbox_usd_override
does not exist**, pull version **19.0.1.1.1**, restart the Odoo service so every
worker loads the fix, refresh the Apps page and retry **Upgrade** on PayBridge.
The fix excludes newly added fields from unrelated automatic ORM reads before
the native upgrade creates their columns. Their stored values, defaults and
normal reads after upgrade are preserved. No uninstall, manual SQL, accounting
override or credential re-entry is required by this patch.

## Configure

1. In **Credentials**, enter the **Test Store ID** and **Test Shared Secret**.
2. Select **Test Mode**. Live credentials are only required when selecting **Enabled**.
3. In the native **Configuration** tab, select the correct **Payment Journal**.
4. In that bank journal's incoming payments, confirm Scotiabank has an
   **Outstanding Receipts** account. Odoo supplies its standard method line.
5. In **Currencies**, allow the Odoo order currencies you accept. Live payments
   require those currencies to be enabled on the live Store ID.
6. Ensure the public Odoo base URL uses HTTPS on port 443.
7. Open **Scotiabank Settings > Check Configuration**. Choose the display mode,
   bank language and sandbox override there. Copy Diagnostics gives a masked summary.
8. Make test payments and complete the acceptance checks in [ACCEPTANCE.md](ACCEPTANCE.md).
9. Enter live credentials and select **Enabled** after successful checks. Use
   Odoo's standard publication/website availability controls.

The configuration button checks local settings. It does **not** contact the bank,
prove the credentials valid, charge a card, or claim a connection is live.

### Sandbox USD override

**Sandbox USD Override** is enabled by default and applies only in **Test Mode**.
It follows the WooCommerce test setup: the bank receives the same numeric amount
in USD (840). For example, a **TTD 600.00** test order sends **USD 600.00** to the
sandbox. This is a **test simulation, not currency conversion**. It is not an FX
quote or a USD settlement for a TTD order. The transaction records the original
Odoo currency and bank currency separately and labels the simulation.

A valid sandbox result proceeds through Odoo's usual test transaction and
accounting behavior using the original document amount/currency. Native Test
Mode can still confirm orders and create accounting records; use test documents.
The bank signature is checked against the saved **USD** request before the
verified response is mapped back to the original Odoo currency for native checks.

When the override is off, Test Mode requires an actual USD order/invoice and USD
allowed on the provider. In **Enabled** mode, the override has no effect: the bank
always receives the actual document currency, and a sandbox response cannot
authorize a live transaction. No production currency override is provided.

### Payment display

| Setting | Customer experience |
| --- | --- |
| Direct redirect (default) | Native Odoo submits the signed form directly to the bank. |
| Branded redirect page | SPXCORP handoff shows the reference and amount before opening the bank page. |
| Embedded payment page | The bank form opens in an iframe inside the Odoo-hosted SPXCORP page. Card data stays at the bank. |

The logo is the original **SPXCORP LTD** asset from the WooCommerce plugin. The
header `#07101f`, button `#0f5bb5`, background `#f5f7fb`, handoff wording and
"Payment integration powered by SPXCORP LTD" attribution match that plugin.
**Show Spxcorp Branding** controls the logo and attribution on handoff pages.
When disabled, the header shows the merchant company name. Direct mode has no
intermediate branded page. **Bank Page Language** defaults to English (UK).

The embedded request includes `parentUri` automatically. The bank's iframe flow
depends on browser privacy/cookie settings and the issuer's 3-D Secure page;
use direct redirect when that flow requires a full page. A bank return exits the
iframe before opening native `/payment/status`. The handoff never interprets
browser messages as payment approval, restores an order session from a bank
reference, or changes Odoo's checkout code.

The authenticated handoff can issue its bank form only once, and the handoff
script guards automatic submission, double-clicks and back/forward restoration.
Reopening an issued handoff goes to native payment status. A new native payment
attempt can have a suffix such as `S00002-1`; changed amounts are separate attempts.
This is not evidence of a duplicate charge. Check the bank and Odoo status before
starting another attempt when the outcome is unknown. The addon does not suppress
Odoo's legitimate retry flow or claim to prevent every bank-side replay.

The notification and return URLs are included in each signed payment request:

```
https://your-odoo-domain/payment/spx_paybridge_scotia/notify
https://your-odoo-domain/payment/spx_paybridge_scotia/return
```

No separate bank activation is required for the standard integration. The HTTPS
domain must reach the correct Odoo database through the normal host/dbfilter
configuration. A login wall, HTTP Basic Auth or proxy challenge must not block
the bank notification route. A browser return alone is not a substitute for
checking that notifications reach this installation.

## References and operations

The standard provider reference is the **Bank Order Reference** sent to Scotiabank.
It contains the Odoo reference prefix and a unique suffix, is searchable at the
gateway, and appears in Odoo's native payment memo. The native transaction also
shows the merchant store, request amount/currency/time, verified approval code,
signature source and notification/return timestamps.

Additional gateway details are labelled **Reported** because the standard bank
signature does not authenticate fields such as the IPG transaction ID. They do
not determine whether Odoo marks a payment successful. The merchant order
reference remains the authoritative cross-system matching reference.

Open a customer payment's **Scotiabank Transaction** button to inspect the normal
payment transaction. Native transaction filters include Scotiabank and payments
awaiting confirmation. No parallel accounting ledger is created.

Only four card digits are retained. Request/response bodies, complete card data,
CVV values, signatures and secret credentials are never written to diagnostic
logs or new transaction payload fields.

Summary logs record internal transaction IDs, original/bank currencies, request
amount and fixed verification outcomes. **Log Transaction Summaries** can disable
routine summaries; verification failures still produce safe warnings. An invalid
or unmatched browser return shows a clear unverified-payment page without changing
financial state. The customer can check the existing native status from there.
HTTP 200 entries for `/payment/status/poll` alone do not prove a bank approval.

If accounting post-processing fails, use Odoo's transaction status and native
post-processing retry after correcting the journal/account configuration. The
gateway callback does not catch and hide accounting failures. Without a browser
return, Odoo's normal scheduled payment post-processing performs the accounting
step after the authenticated bank notification.

## Supported scope

Hosted **sale** payments; standard approvals, declines and waiting responses;
duplicate and out-of-order callback protection; separate test/live settings;
native invoice/order/payment linkage; standard reconciliation.

This release does not implement gateway refunds, manual authorization/capture,
voids, stored cards, subscription charging, transaction-inquiry polling or bank
settlement imports. Odoo is told these provider capabilities are unavailable.
Ordinary accounting credit notes and bank-side refunds retain their normal
workflows; this module does not synchronize them automatically.

## Security and protocol scope

The standard response hash covers approval code, amount, currency, original
request time and Store ID. PayBridge verifies those fields against a saved,
immutable attempt and allocates a unique real UTC second for each Store ID in
the database. A database uniqueness constraint and serialized allocation prevent
same-timestamp attempts. Simultaneous starts can briefly wait for the next second.

Use one active integration/database for a merchant Store ID. Independently
operated systems sharing the same Store ID and secret are outside this
single-database replay guarantee: the standard protocol does not sign the order
ID. Test restored databases with test credentials, not live credentials.

The standard signature also does not authenticate partial-approval metadata.
Split-tender/partial card authorization is outside this release; responses
reporting partial approval are held for review, never deliberately finalized
as full payment. The release is for the existing full-sale card flow.

The optional extended-response feature is not required or configured.
See [VALIDATION.md](VALIDATION.md) for the exact checks executed and limitations.

## Developer checks

Run the following commands from the repository root. The checker and all
installation notes are included inside the module folder.

Offline protocol/syntax checks (standard Python only):

```bash
python spx_paybridge_scotia/tools/check_module.py
node --test spx_paybridge_scotia/tests/test_checkout.mjs
```

Real Odoo import and HTTP parser checks, using an environment with Odoo's Python dependencies:

```bash
python spx_paybridge_scotia/tools/check_module.py --odoo-root /path/to/odoo19
```

Odoo 19 Enterprise database tests, on a disposable test database only:

```bash
./odoo-bin -d paybridge_test --addons-path=odoo/addons,enterprise,/path/to/this/repository -i spx_paybridge_scotia --test-enable --test-tags /spx_paybridge_scotia --stop-after-init
```

Those database tests exercise real native payment creation, invoice matching,
duplicate handling and rollback/retry. They use synthetic bank messages and do
not contact the bank. They complement the actual bank sandbox acceptance run.
