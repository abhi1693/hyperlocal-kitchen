"use client";
import Link from "next/link";
import { useState } from "react";
import {
  useAdminOrderGet,
  adminOrderAccept,
  adminOrderReject,
  adminOrderPrepare,
  adminOrderReady,
  adminOrderComplete,
  adminOrderCancel,
  adminOrderReportPayment,
  adminOrderConfirmPayment,
} from "@/lib/api/generated/admin";
import { availableOrderActions, orderActionLabels, type OrderAction } from "@/lib/order-actions";
import type { OrderOut } from "@/lib/api/generated/models";
import { money } from "@/lib/utils";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Combobox } from "@/components/molecules/combobox";
import { Textarea } from "@/components/atoms/textarea";
import { ResourceForm } from "@/components/organisms/resource-form";
import { PageHeading } from "@/components/molecules/page-heading";
import { StatusBadge } from "@/components/molecules/status-badge";

export function OrderActionPage({ id, action }: { id: string; action?: OrderAction }) {
  const query = useAdminOrderGet(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  return <Editor key={`${id}/${action ?? "edit"}`} order={query.data} action={action} />;
}
function Editor({ order, action }: { order: OrderOut; action?: OrderAction }) {
  const actions = availableOrderActions(order);
  const [selected, setSelected] = useState<OrderAction>(action ?? actions[0] ?? "accept");
  if (!actions.length || (action && !actions.includes(action)))
    return (
      <section className="max-w-4xl space-y-6">
        <PageHeading
          title={action ? orderActionLabels[action] : "Edit order"}
          description={`Order #${order.order_number}`}
        />
        <p role="alert">This action is unavailable for the order’s current state.</p>
        <Link href={`/orders/${order.id}`} className="underline">
          Back to order
        </Link>
      </section>
    );
  return (
    <ResourceForm
      cancelHref={`/orders/${order.id}`}
      title={action ? orderActionLabels[action] : "Edit order"}
      description={`Order #${order.order_number} · ${order.customer_name} · ${order.kitchen_name}`}
      submit={(data) => {
        if (!availableOrderActions(order).includes(selected))
          throw new Error("This action is no longer available. Reload the order.");
        const id = order.id;
        switch (selected) {
          case "accept":
            return adminOrderAccept(id);
          case "reject":
            return adminOrderReject(id, { reason: String(data.get("reason")) });
          case "prepare":
            return adminOrderPrepare(id);
          case "ready":
            return adminOrderReady(id);
          case "complete":
            return adminOrderComplete(id);
          case "cancel":
            return adminOrderCancel(id);
          case "report-payment":
            return adminOrderReportPayment(id);
          case "confirm-payment":
            return adminOrderConfirmPayment(id);
        }
      }}
    >
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <StatusBadge value={order.status} />
        <StatusBadge value={order.payment_status} />
        <span>{money(order.total_paise)}</span>
      </div>
      {!action && (
        <Field label="Order action" id="order_action">
          <Combobox
            id="order_action"
            label="Order action"
            value={selected}
            onValueChange={(value) => setSelected(value as OrderAction)}
            options={actions.map((value) => ({ value, label: orderActionLabels[value] }))}
          />
        </Field>
      )}
      {selected === "reject" && (
        <Field id="reject_reason" label="Reason">
          <Textarea id="reject_reason" name="reason" required maxLength={300} />
        </Field>
      )}
      {selected === "cancel" && (
        <p className="text-sm">
          Cancel this order and release its reserved portions. The order and its history will remain
          available.
        </p>
      )}
      {selected === "confirm-payment" && (
        <p className="text-sm">
          Acknowledge that the kitchen received this payment. This does not charge the customer.
        </p>
      )}
      {selected === "report-payment" && (
        <p className="text-sm">
          Record that the customer reported making a payment. The kitchen must still confirm
          receipt.
        </p>
      )}
      <p className="text-sm text-muted-foreground">
        Placed items, prices and delivery details are retained. Changes are recorded in the order
        history.
      </p>
    </ResourceForm>
  );
}
