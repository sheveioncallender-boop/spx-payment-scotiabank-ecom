/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
// Ensure the native online-payment extensions are applied before this adapter.
import "@pos_online_payment/app/services/pos_store";
import "@pos_online_payment/app/utils/order_payment_validation";

const completions = new WeakMap();
const watchers = new WeakMap();
const hasScotiaPayment = (order) =>
    order.payment_ids.some((line) => line.payment_method_id.spx_scotia_online);
const isPaid = (order) => order && ["paid", "done", "invoiced"].includes(order.state);

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        // A notification is a hint only. The authenticated native RPC below is
        // the authority; no state is inferred from a notification or bank URL.
        this.data.connectWebSocket("ONLINE_PAYMENTS_NOTIFICATION", ({ id }) => {
            const order = this.models["pos.order"].get(id);
            if (order?.uiState.spxScotiaPending) {
                this.spxWatchScotiaOrder(order);
            }
        });
        for (const order of this.models["pos.order"].getAll()) {
            if (order.uiState.spxScotiaPending) {
                this.spxWatchScotiaOrder(order);
            }
        }
    },

    spxWatchScotiaOrder(order) {
        if (watchers.has(order) || order.uiState.spxScotiaCompleted) {
            return;
        }
        order.uiState.spxScotiaPending = true;
        const check = async () => {
            if (!this.models["pos.order"].getBy("uuid", order.uuid) ||
                order.state === "cancel" || order.uiState.spxScotiaCompleted ||
                !hasScotiaPayment(order)) {
                watchers.delete(order);
                order.uiState.spxScotiaPending = false;
                return;
            }
            try {
                if (order.isSynced) {
                    // false means read only: do not reset an amount or create a payment.
                    const data = await this.data.call(
                        "pos.order", "get_and_set_online_payments_data", [order.id, false]
                    );
                    if (data?.id === order.id && isPaid(data.paid_order?.[0])) {
                        await new OrderPaymentValidation({
                            pos: this, orderUuid: order.uuid,
                        }).afterPaidOrderSavedOnServer(data.paid_order);
                    }
                }
            } catch (error) {
                // Keep the existing order intact and retry after a reconnect.
                // Do not log payloads, tokens or bank details.
                console.warn("PayBridge: POS completion will retry after a failed refresh.");
            }
            if (order.uiState.spxScotiaCompleted) {
                watchers.delete(order);
            } else {
                watchers.set(order, setTimeout(check, 5000));
            }
        };
        watchers.set(order, setTimeout(check, 1000));
    },
});

patch(OrderPaymentValidation.prototype, {
    async isOrderValid() {
        if (hasScotiaPayment(this.order) && !this.order.finalized) {
            this.pos.spxWatchScotiaOrder(this.order);
        }
        return await super.isOrderValid(...arguments);
    },

    async afterPaidOrderSavedOnServer(orderJSON) {
        const order = this.order;
        if (!hasScotiaPayment(order) && !order.uiState.spxScotiaPending) {
            return await super.afterPaidOrderSavedOnServer(...arguments);
        }
        if (order.uiState.spxScotiaCompleted) {
            return;
        }
        if (completions.has(order)) {
            return await completions.get(order);
        }
        // Never finalize from an incomplete response or another order's response.
        if (orderJSON?.[0]?.id !== order.id || !isPaid(orderJSON[0])) {
            return;
        }
        const complete = async () => {
            // Use Odoo's full POS serializer, including persisted payment IDs.
            // Merely setting state='paid' leaves the temporary QR line behind.
            let data = await this.pos.data.call(
                "pos.order", "read_pos_orders", [[["id", "=", order.id]]]
            );
            const saved = data?.["pos.order"]?.find((row) => row.id === order.id);
            if (!isPaid(saved)) {
                throw new Error("PayBridge: confirmed POS order could not be refreshed");
            }
            data = await this.pos.data.missingRecursive(data);
            // Resolve the native QR waiter before removing its local placeholder.
            // This also closes the native popup through its existing success flow.
            for (const line of [...order.payment_ids]) {
                line.onlinePaymentResolver?.(true);
                if (!line.isSynced && line.payment_method_id.is_online_payment) {
                    // Local-only line. Never unlink a persisted payment or accounting record.
                    line.delete({ silent: true });
                }
            }
            const loaded = this.pos.models.connectNewData(data);
            const paidOrder = loaded["pos.order"].find((row) => row.id === order.id);
            if (!paidOrder) {
                throw new Error("PayBridge: POS order missing from native response");
            }
            paidOrder.serializeForORM();
            this.pos.data.synchronizeServerDataInIndexedDB(data);
            // The regular paid-order sync hook owns loyalty confirmation, card
            // updates and reward linkage. Do not calculate or write points here.
            await this.pos.postSyncAllOrders([paidOrder]);
            this.pos.removePendingOrder(paidOrder);
            if (this.pos.getOrder()?.uuid === paidOrder.uuid) {
                await super.afterPaidOrderSavedOnServer(data["pos.order"]);
            }
            // If staff moved to another ticket, leave their current screen alone.
            paidOrder.uiState.spxScotiaCompleted = true;
            paidOrder.uiState.spxScotiaPending = false;
        };
        const pending = complete();
        completions.set(order, pending);
        try {
            return await pending;
        } finally {
            completions.delete(order);
        }
    },
});
