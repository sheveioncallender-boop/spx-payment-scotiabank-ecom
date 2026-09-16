# Spxcorp PayBridge - Scotiabank eCom+

Fresh payment provider for **Odoo 19 Enterprise**, by **Spxcorp Limited**.

The complete new module is in [`spx_paybridge_scotia`](spx_paybridge_scotia/),
version **19.0.1.1.1**, on branch **rebuild-odoo19-enterprise**.
Pull/redeploy that branch through Cloudpepper, then install **Spxcorp PayBridge**.
If already installed, **upgrade the app** after pulling; updating the Apps list
alone does not install the new settings and transaction fields.
The manifest must be at `spx_paybridge_scotia/__manifest__.py`.

Version 1.1.1 fixes the `scotia_sandbox_usd_override does not exist` error that
could prevent an Apps upgrade after new code was loaded against the old schema.
Pull the latest branch, restart Odoo, then retry the PayBridge upgrade in Apps.

Includes the original SPXCORP branded handoff, embedded or direct bank pages,
a sandbox-only USD override, and diagnostics. Odoo owns transaction creation,
order confirmation, payments, invoices and reconciliation.

- [Installation and configuration](spx_paybridge_scotia/README.md)
- [Cloudpepper acceptance checks](spx_paybridge_scotia/ACCEPTANCE.md)
- [Executed validation and remaining tests](spx_paybridge_scotia/VALIDATION.md)

This is a fresh module identity, not an upgrade or migration of the earlier app.
The existing `spx_payment_scotiabank_ecom` folder is preserved for prior deployments.

Run the local protocol checks from the repository root:

```bash
python spx_paybridge_scotia/tools/check_module.py
```
