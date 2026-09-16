# PayBridge acceptance on Odoo 19 Enterprise

Run against a fresh test installation, using the bank's existing test credentials
and bank-supplied test card cases. No additional account feature is required.

| Check | Expected result |
| --- | --- |
| Fresh install | PayBridge installs, Scotiabank provider starts Disabled, credential fields are empty. |
| Missing credentials | Test/Enabled activation requires credentials for that mode only. |
| Journal setup | The normal bank journal has one incoming payment method for this provider and an Outstanding Receipts account. |
| Currency | The actual order/invoice currency matches the gateway; no currency override exists. |
| Approved invoice | Native transaction becomes Done. Odoo creates one customer payment, posts its journal entry and matches the invoice receivable. |
| Declined invoice | Transaction becomes Error; no customer payment or successful accounting entry is created. |
| Customer cancellation | A signed negative bank result remains unsuccessful; no browser parameter can mark an order paid. |
| Waiting bank result | Signed waiting approval code produces Pending; later bank approval completes the same transaction. |
| Website order, if eCommerce installed | Normal Odoo payment selection, status page, order confirmation and sale order processing continue. |
| Quotation payment, if Sales installed | The native portal payment link follows the normal sales workflow. |
| Closed checkout tab | A valid server notification updates the transaction; Odoo's scheduled post-processing creates the normal payment without a browser return. |
| Duplicate notification | Only one customer payment and one set of accounting effects exist. |
| Late decline after success | Done is preserved and references are not overwritten. |
| Altered approval/amount/currency | Signature verification rejects the message without mutating transaction or accounting state. |
| Replay on another order | The stored request timestamp and amount/currency binding reject reuse on another attempt. |
| Missing customer phone | Hosted form prepares successfully. |
| Session missing/expired | The bank result can still be processed; no order is granted to the browser from a supplied reference. Standard Odoo status may say the payment cannot be found in that session. |
| Callback delivery | Both return and notification timestamps are visible when both messages arrive. |
| Native reconciliation | Match the real bank statement/settlement using the ordinary reconciliation screen. Account for fees normally; PayBridge does not invent deposits. |
| Native posting failure | Correct the journal/account setup and retry through Odoo. A failed posting must not remain falsely post-processed. |
| Credentials and logs | Secrets remain administrator-only; callback bodies and card data do not appear in logs. |
| Multi-company, if used | Each company has its own provider configuration and journal, with no copied secrets. |

Do not use a successful local configuration check as evidence that a bank payment
was accepted. Record bank sandbox references and the resulting Odoo transaction,
customer payment, journal entry and invoice status for the acceptance run.

Sandbox-only USD setup: create a real USD quotation/invoice or USD website
pricelist. Do not test a TTD invoice by changing only the currency label sent to
the gateway.
