# Spxcorp PayBridge - Scotiabank eCom+

Fresh payment provider for **Odoo 19 Enterprise**, by **Spxcorp Limited**.

The complete new module is in [`spx_paybridge_scotia`](spx_paybridge_scotia/).
Extract the delivery ZIP and upload that one folder directly to this repository
root, then pull/redeploy through Cloudpepper and install **Spxcorp PayBridge**.
The manifest must be at `spx_paybridge_scotia/__manifest__.py`.

- [Installation and configuration](spx_paybridge_scotia/README.md)
- [Cloudpepper acceptance checks](spx_paybridge_scotia/ACCEPTANCE.md)
- [Executed validation and remaining tests](spx_paybridge_scotia/VALIDATION.md)

This is a fresh module identity, not an upgrade or migration of the earlier app.
The existing `spx_payment_scotiabank_ecom` folder is preserved for prior deployments.

Run the local protocol checks from the repository root:

```bash
python spx_paybridge_scotia/tools/check_module.py
```
