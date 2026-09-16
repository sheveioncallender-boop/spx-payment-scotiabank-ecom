import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../static/src/js/checkout.js", import.meta.url), "utf8");
function page({ embedded = false, bridge = null } = {}) {
    const handlers = {};
    const timers = [];
    const navigations = [];
    let posts = 0;
    const form = { addEventListener: (name, fn) => { handlers[name] = fn; } };
    const button = { disabled: false, hidden: false };
    const spinner = { hidden: false };
    const frame = embedded ? { addEventListener: (name, fn) => { handlers[`frame:${name}`] = fn; } } : null;
    const elements = { "spx-bank-form": form, "spx-continue": button, "spx-bank-frame": frame,
        "spx-loading": spinner, "spx-return": bridge ? { getAttribute: () => bridge } : null };
    const window = {
        addEventListener: (name, fn) => { handlers[name] = fn; },
        setTimeout: fn => { timers.push(fn); },
        location: { replace: url => navigations.push(url) },
        top: { location: { replace: url => navigations.push(url) } },
    };
    runInNewContext(source, { document: { getElementById: id => elements[id] }, window,
        HTMLFormElement: { prototype: { submit() { assert.equal(this, form); posts++; } } } });
    return { handlers, timers, navigations, button, spinner, posts: () => posts };
}

test("click plus auto-submit plus repeated click sends one bank form", () => {
    const p = page();
    p.handlers.submit({ preventDefault() {} });
    p.timers[0]();
    p.handlers.submit({ preventDefault() {} });
    assert.equal(p.posts(), 1);
    assert.equal(p.button.disabled, true);
});
test("embedded mode submits once and hides the launch button", () => {
    const p = page({ embedded: true });
    p.timers[0]();
    p.handlers["frame:load"]();
    assert.equal(p.posts(), 1);
    assert.equal(p.button.hidden, true);
    assert.equal(p.spinner.hidden, true);
});
test("back-forward cache goes to native status without another bank post", () => {
    const p = page();
    p.handlers.pageshow({ persisted: true });
    p.timers[0]();
    assert.equal(p.posts(), 0);
    assert.deepEqual(p.navigations, ["/payment/status"]);
});
test("bank return exits to the native top-level status page", () => {
    const p = page({ bridge: "/payment/status" });
    assert.deepEqual(p.navigations, ["/payment/status"]);
    assert.equal(p.posts(), 0);
});
test("unverified bank response opens the local explanation", () => {
    const target = "/payment/spx_paybridge_scotia/unverified";
    assert.deepEqual(page({ bridge: target }).navigations, [target]);
});
test("bridge refuses arbitrary and external redirect targets", () => {
    for (const target of ["https://example.test", "//example.test", "/other", "javascript:alert(1)"]) {
        assert.deepEqual(page({ bridge: target }).navigations, []);
    }
});
