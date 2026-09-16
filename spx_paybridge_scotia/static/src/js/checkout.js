/* Standalone handoff only. Native Odoo owns checkout and payment status. */
(() => {
    "use strict";
    const returnLink = document.getElementById("spx-return");
    if (returnLink) {
        // The server renders only these fixed local destinations. No bank message
        // or postMessage event can select a target or mark a payment successful.
        const target = returnLink.getAttribute("href");
        if (["/payment/status", "/payment/spx_paybridge_scotia/unverified"].includes(target)) {
            try { window.top.location.replace(target); } catch { /* Accessible link remains. */ }
        }
        return;
    }
    const form = document.getElementById("spx-bank-form");
    if (!form) { return; }
    const button = document.getElementById("spx-continue");
    const frame = document.getElementById("spx-bank-frame");
    let submitted = false;
    const submitOnce = () => {
        if (submitted) { return; }
        submitted = true;
        button.disabled = true;
        // Bypass this page's submit listener once, without creating an Odoo tx.
        HTMLFormElement.prototype.submit.call(form);
        if (frame) { button.hidden = true; }
    };
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitOnce();
    });
    if (frame) {
        frame.addEventListener("load", () => {
            if (submitted) { document.getElementById("spx-loading").hidden = true; }
        });
    }
    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            // Back/forward cache must not reopen an already issued bank form.
            submitted = true;
            button.disabled = true;
            window.location.replace("/payment/status");
        }
    });
    window.setTimeout(submitOnce, frame ? 0 : 700);
})();
