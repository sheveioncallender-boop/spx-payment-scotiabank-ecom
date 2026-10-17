import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

// Execute the shipping extension. These are orchestration regression tests;
// they do not replace the Odoo browser/bank acceptance test after deployment.
const source = readFileSync(new URL("../static/src/online_payment.js", import.meta.url), "utf8")
    .replace(/^import .*;\n/gm, "");
function patch(target, extension) {
    const previous = Object.create(Object.getPrototypeOf(target));
    Object.defineProperties(previous, Object.getOwnPropertyDescriptors(target));
    Object.setPrototypeOf(extension, previous);
    Object.defineProperties(target, Object.getOwnPropertyDescriptors(extension));
}
function fixture({ scotia = true, switched = false, state = "paid", failRead = false,
    partial = false, cash = false, serverId = 7, skipAdapter = false } = {}) {
    const timers = [];
    const calls = [];
    const notifications = [];
    const deleted = [];
    let confirmations = 0;
    let receipts = 0;
    let resolved = 0;
    let warnings = 0;
    const method = { is_online_payment: true, spx_scotia_online: scotia };
    const order = {
        id: 7, uuid: "order-7", isSynced: true, state: "draft", finalized: false,
        uiState: { couponPointChanges: { 42: { points: 15, coupon_id: 42 } } },
        isToInvoice: () => false, isPaidWithCash: () => false, change: 0,
        payment_ids: [], serializeForORM() { calls.push("clear-commands"); },
    };
    const makeLine = (id, paymentMethod = method) => ({
        id, isSynced: typeof id === "number", amount: cash ? 10 : 15,
        payment_method_id: paymentMethod,
        onlinePaymentResolver: typeof id === "string" ? () => { resolved++; } : undefined,
        delete(options) {
            assert.equal(options.silent, true);
            assert.equal(this.isSynced, false, "must never delete a persisted payment");
            deleted.push(id);
            order.payment_ids = order.payment_ids.filter((line) => line !== this);
        },
    });
    order.payment_ids = [makeLine("temporary-qr"), makeLine(80)];
    if (cash) order.payment_ids.push(makeLine(81, { is_online_payment: false }));
    const serverPayments = order.payment_ids.filter((line) => line.isSynced);
    const saved = { id: serverId, uuid: order.uuid, state, payment_ids: serverPayments.map(p => p.id) };
    const response = { "pos.order": [saved], "pos.payment": serverPayments };
    class PosStore {
        async setup() {}
        async postSyncAllOrders(orders) {
            assert.equal(orders[0].state, state);
            assert.equal(orders[0].uiState.couponPointChanges[42].points, 15);
            confirmations++;
            calls.push("native-loyalty-hook");
        }
        removePendingOrder(o) { assert.equal(o, order); calls.push("remove-pending"); }
        getOrder() { return switched ? { uuid: "other-ticket" } : order; }
    }
    class OrderPaymentValidation {
        constructor({ pos, orderUuid }) { this.pos = pos; this.orderUuid = orderUuid; }
        get order() { return order; }
        async isOrderValid() { calls.push("native-validation"); return false; }
        get nextPage() { return { page: "ReceiptScreen", params: { orderUuid: order.uuid } }; }
        async postPushOrderResolve() { calls.push("native-post-push"); }
        async afterOrderValidation() { calls.push("native-receipt"); receipts++; }
        async afterPaidOrderSavedOnServer(rows) {
            assert.equal(rows[0].id, order.id);
            calls.push("native-receipt");
            receipts++;
        }
    }
    if (process.env.ODOO_ROOT) {
        const nativeSource = readFileSync(`${process.env.ODOO_ROOT}/addons/pos_online_payment/static/src/app/utils/order_payment_validation.js`, "utf8")
            .replace(/^import .*;\n/gm, "");
        runInNewContext(nativeSource, { patch, OrderPaymentValidation });
    }
    if (!skipAdapter) runInNewContext(source, { patch, PosStore, OrderPaymentValidation,
        setTimeout(fn, delay) { timers.push({ fn, delay }); return timers.length; },
        console: { warn() { warnings++; } },
    });
    const pos = new PosStore();
    pos.config = {};
    pos.validated_orders_name_server_id_map = {};
    pos.navigate = () => calls.push("native-navigate");
    pos.models = {
        "pos.order": { get: id => id === order.id ? order : undefined,
            getBy: (_, uuid) => uuid === order.uuid ? order : undefined, getAll: () => [order] },
        connectNewData(data) {
            calls.push("load-native-records");
            // Native related_models retains unsynced x2many records on read.
            // This reproduces the original duplicate receipt regression.
            const temporary = order.payment_ids.filter(p => !p.isSynced);
            order.payment_ids = [...temporary, ...data["pos.payment"]];
            order.state = data["pos.order"][0].state;
            order.finalized = true;
            return { "pos.order": [order] };
        },
    };
    pos.data = {
        connectWebSocket(channel, fn) { notifications.push(fn); },
        async call(model, methodName, args) {
            calls.push(methodName);
            assert.equal(model, "pos.order");
            if (methodName === "read_pos_orders") {
                assert.deepEqual(JSON.parse(JSON.stringify(args)), [[["id", "=", 7]]]);
                if (failRead) throw new Error("offline");
                return response;
            }
            assert.equal(methodName, "get_and_set_online_payments_data");
            assert.equal(args[1], false, "status refresh must be read-only");
            return partial ? { id: order.id, amount_unpaid: 5, online_payments: [] }
                : { id: order.id, paid_order: [saved] };
        },
        async missingRecursive(data) { return data; },
        synchronizeServerDataInIndexedDB() { calls.push("cache-native-records"); },
    };
    const validation = () => new OrderPaymentValidation({ pos, orderUuid: order.uuid });
    return { pos, order, saved, validation, timers, calls, deleted, notifications,
        counts: () => ({ confirmations, receipts, resolved, warnings }),
        async tick() { const next = timers.shift(); assert.ok(next); await next.fn(); },
    };
}

test("paid receipt uses one persisted online line and the native loyalty hook", async () => {
    const f = fixture();
    await f.validation().afterPaidOrderSavedOnServer([f.saved]);
    assert.deepEqual(f.order.payment_ids.map(p => p.id), [80]);
    assert.deepEqual(f.deleted, ["temporary-qr"]);
    assert.equal(f.order.payment_ids.reduce((sum, p) => sum + p.amount, 0), 15);
    assert.equal(f.counts().confirmations, 1);
    assert.equal(f.counts().receipts, 1);
    assert.ok(f.calls.indexOf("native-loyalty-hook") < f.calls.indexOf("native-receipt"));
});
test("concurrent callback and polling finalize once", async () => {
    const f = fixture();
    await Promise.all([f.validation().afterPaidOrderSavedOnServer([f.saved]),
        f.validation().afterPaidOrderSavedOnServer([f.saved])]);
    await f.validation().afterPaidOrderSavedOnServer([f.saved]);
    assert.equal(f.counts().confirmations, 1);
    assert.equal(f.counts().receipts, 1);
});
test("missing browser notification recovers without a second Validate click", async () => {
    const f = fixture();
    await f.validation().isOrderValid();
    await f.tick();
    assert.equal(f.counts().receipts, 1);
    assert.equal(f.order.uiState.spxScotiaCompleted, true);
    assert.equal(f.timers.length, 0);
});
test("switching tickets still completes loyalty without changing cashier screen", async () => {
    const f = fixture({ switched: true });
    await f.validation().isOrderValid();
    await f.tick();
    assert.equal(f.counts().confirmations, 1);
    assert.equal(f.counts().receipts, 0);
    assert.equal(f.order.uiState.spxScotiaCompleted, true);
});
test("mixed cash and online payments retain every persisted payment", async () => {
    const f = fixture({ cash: true });
    await f.validation().afterPaidOrderSavedOnServer([f.saved]);
    assert.deepEqual(f.order.payment_ids.map(p => p.id), [80, 81]);
    assert.deepEqual(f.deleted, ["temporary-qr"]);
});
for (const state of ["draft", "cancel"]) {
    test(`${state} server order cannot complete or award points`, async () => {
        const f = fixture({ state });
        await f.validation().afterPaidOrderSavedOnServer([f.saved]);
        assert.equal(f.counts().confirmations, 0);
        assert.equal(f.deleted.length, 0);
    });
}
test("partial payment stays open and earns no points", async () => {
    const f = fixture({ partial: true });
    await f.validation().isOrderValid();
    await f.tick();
    assert.equal(f.counts().confirmations, 0);
    assert.equal(f.counts().receipts, 0);
    assert.equal(f.timers.length, 1);
});
test("wrong order response cannot finalize or delete local lines", async () => {
    const f = fixture({ serverId: 8 });
    await f.validation().afterPaidOrderSavedOnServer([f.saved]);
    assert.equal(f.counts().confirmations, 0);
    assert.equal(f.deleted.length, 0);
});
test("refresh failure keeps local lines and retries without creating a payment", async () => {
    const f = fixture({ failRead: true });
    await f.validation().isOrderValid();
    await f.tick();
    assert.equal(f.deleted.length, 0);
    assert.equal(f.counts().confirmations, 0);
    assert.equal(f.counts().warnings, 1);
    assert.equal(f.timers.length, 1);
});
test("other providers retain native behavior without polling", async () => {
    const f = fixture({ scotia: false });
    await f.validation().isOrderValid();
    await f.validation().afterPaidOrderSavedOnServer([f.saved]);
    assert.equal(f.timers.length, 0);
    assert.equal(f.counts().confirmations, 0);
    assert.equal(f.counts().receipts, 1);
    assert.equal(f.deleted.length, 0);
});
test("pending online completion resumes after a POS reload", async () => {
    const f = fixture();
    f.order.uiState.spxScotiaPending = true;
    await f.pos.setup();
    await f.tick();
    assert.equal(f.counts().confirmations, 1);
});
test("repeated notifications do not create additional timers or completions", async () => {
    const f = fixture();
    await f.pos.setup();
    await f.validation().isOrderValid();
    f.notifications[0]({ id: 7 });
    f.notifications[0]({ id: 7 });
    assert.equal(f.timers.length, 1);
    await f.tick();
    assert.equal(f.counts().confirmations, 1);
});
test("cancelled order stops status checks", async () => {
    const f = fixture();
    await f.validation().isOrderValid();
    f.order.state = "cancel";
    await f.tick();
    assert.equal(f.counts().confirmations, 0);
    assert.equal(f.timers.length, 0);
});

if (process.env.ODOO_ROOT) {
    test("unpatched Odoo reproduces duplicate receipt and skipped loyalty hook", async () => {
        const f = fixture({ skipAdapter: true });
        await f.validation().afterPaidOrderSavedOnServer([f.saved]);
        assert.equal(f.order.payment_ids.length, 2);
        assert.equal(f.counts().confirmations, 0);
        assert.equal(f.counts().receipts, 1);
    });
}
