# PayBridge validation record

Target: **Odoo 19 Enterprise**, fresh module `spx_paybridge_scotia`, version
`19.0.1.0.0`. No live merchant credentials were used.

## Executed locally

| Check | Result |
| --- | --- |
| Python syntax for all new module files | Passed |
| XML parsing and declared manifest files | Passed |
| Explicit Enterprise Accounting dependency | Confirmed: `account_accountant` |
| Actual module import against Odoo 19.0 source and its Python dependencies | Passed |
| Protocol tests | 25 passed |
| HTTP body/parser tests using Werkzeug and the real controller module | 8 passed |
| Inherited view insertion targets against current Odoo 19 source | All 6 matched |
| Request HMAC against the published Fiserv manual vector | Passed |
| Fresh application identity and isolated callback paths | Confirmed |

The protocol cases cover approvals, declines, waiting states, missing/invalid
signatures, amount and currency mismatches, attempted cross-order replay,
tampered approval/status fields, notification signature ordering, previous-key
rotation, missing echoed merchant/time fields, invalid/nonfinite amounts,
reported partial approvals and card-data reduction to four digits.

The HTTP cases include Odoo's already-parsed form behaviour, query/body
separation, duplicate parameters, content type, Unicode/Base64 preservation,
and body/field size limits.

Odoo reference source checked: branch `19.0`, commit
`cee9ee44f3c21c5d01592d8fff520f1bb2840145`. The inspected provider, transaction,
account_payment, status-page and website-checkout code is Odoo's public shared
foundation used by Enterprise. Proprietary Enterprise addons were not present
in the local runtime.

## Included, but not executed here

`tests/test_native_flow.py` contains 10 Odoo database integration tests for:

- Native incoming payment creation, posting, invoice matching and reference linkage.
- Duplicate callbacks and idempotent native post-processing.
- Invalid notifications leaving state and accounting untouched.
- Same-amount cross-order replay rejection.
- Signed declines with forged unsigned status fields.
- Late negative callbacks after success.
- Original test credentials after a provider-mode switch.
- Customers without a telephone number.
- Native accounting failure rollback and subsequent retry.
- Provider-copy credential protection and correct capability declarations.

A functioning PostgreSQL-backed Odoo Enterprise installation was not available
locally, so the module has **not** been installed into an Enterprise database in
this environment and these 10 database tests have **not** been executed. An
import check is not an installation or accounting-posting test.

No real Scotiabank test/live payment, notification-delivery test, 3-D Secure
challenge, bank settlement or production deployment was performed. Complete
`ACCEPTANCE.md` on the new Cloudpepper test instance before live payments.

## Design boundaries

No manual invoice-state changes, direct ledger creation, parallel payment
tables, bank inquiry simulation, custom post-processing scheduler or public
order-session restoration is implemented. The integration updates the native
transaction through Odoo's hooks; Odoo owns the financial post-processing.

The standard gateway protocol has a narrower signed field set than a full
response signature. Attempt matching uses the stored amount, currency, merchant
and a unique original request time. Its guarantee is scoped to this active
database/Store ID. Other gateway fields remain reported metadata; they never
authorize payment. The optional bank signature feature is not required.
