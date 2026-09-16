# Spxcorp PayBridge - Scotiabank eCom+

A fresh payment-provider module for **Odoo 19 Enterprise** by **Spxcorp Limited**.

- App: **Spxcorp PayBridge - Scotiabank eCom+**
- Technical module and provider code: `spx_paybridge_scotia`
- Version: `19.0.1.0.0`
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
2. Extract the delivery ZIP. It contains one folder: `spx_paybridge_scotia`.
3. In this GitHub repository, use **Add file > Upload files**, drag in that whole
   folder, and commit. It belongs directly at the repository root, so the manifest
   is `spx_paybridge_scotia/__manifest__.py`.
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

## Configure

1. In **Credentials**, enter the **Test Store ID** and **Test Shared Secret**.
2. Select **Test Mode**. Live credentials are only required when selecting **Enabled**.
3. In the native **Configuration** tab, select the correct **Payment Journal**.
4. In that bank journal's incoming payments, confirm Scotiabank has an
   **Outstanding Receipts** account. Odoo supplies its standard method line.
5. Restrict **Currencies** to those already enabled for this Store ID.
6. Ensure the public Odoo base URL uses HTTPS on port 443.
7. Open **Scotiabank Connection > Check Configuration**.
8. Make test payments and complete the acceptance checks in [ACCEPTANCE.md](ACCEPTANCE.md).
9. Enter live credentials and select **Enabled** after successful checks. Use
   Odoo's standard publication/website availability controls.

The configuration button checks local settings. It does **not** contact the bank,
prove the credentials valid, charge a card, or claim a connection is live.

For a USD-only test Store ID, make the actual test order/invoice **USD** and allow
USD on the provider. A TTD amount is never relabelled as USD. There are no amount
or currency override settings.

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
