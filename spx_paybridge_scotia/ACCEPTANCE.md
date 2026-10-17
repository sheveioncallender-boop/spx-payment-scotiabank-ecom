# PayBridge acceptance on Odoo 19 Enterprise

Run against a fresh test installation, using the bank's existing test credentials
and bank-supplied test card cases. No additional account feature is required.

| Check | Expected result |
| --- | --- |
| Fresh install | PayBridge installs, Scotiabank provider starts Disabled, credential fields are empty. |
| Missing credentials | Test/Enabled activation requires credentials for that mode only. |
| Journal setup | The normal bank journal has one incoming payment method for this provider and an Outstanding Receipts account. |
| Sandbox override on | A TTD 600 test document sends 600.00 / 840 to the sandbox. Odoo retains TTD 600; transaction and handoff label the USD simulation. |
| Sandbox override off | Non-USD documents cannot start this test provider. An actual USD document can. |
| Live currency | Enabled mode sends actual order currency, including TTD 780, even with the sandbox override selected. |
| Display options | Direct, original SPXCORP branded, and embedded pages open the bank form with one unchanged reference and amount. |
| Branding / language | Branding toggle hides/shows the original logo and attribution; selected language reaches the bank. |
| Repeat handoff | Double-click, auto-submit and re-opening the same issued handoff do not produce another bank form. Check unknown outcomes before starting a new native attempt. |
| Embedded 3-D Secure | Complete the issuer challenge; callback returns to top-level native Odoo status. Test target browsers; use direct redirect if a browser/issuer does not support framing. |
| Unverified return | Clear unverified-payment message; no success/accounting mutation from an invalid signature or unknown reference. |
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

Test Mode can still create normal Odoo orders/payments/accounting entries. Use
test documents and inspect original/bank currencies in the transaction. The
sandbox override simulates the numeric amount in USD; it does not perform FX
conversion or affect live payments. No test-mode flag is used to bypass signature
verification or Odoo's normal post-processing.
