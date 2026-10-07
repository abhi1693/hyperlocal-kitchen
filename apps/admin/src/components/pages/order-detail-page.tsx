"use client";
import Link from "next/link";
import {
  useAdminOrderGet,
  adminOrderAccept,
  adminOrderReject,
  adminOrderPrepare,
  adminOrderReady,
  adminOrderComplete,
  adminOrderCancel,
  adminOrderConfirmPayment,
  adminOrderReportPayment,
} from "@/lib/api/generated/admin";
import { money, dateTime } from "@/lib/utils";
import { PageHeading } from "@/components/molecules/page-heading";
import { QueryState } from "@/components/molecules/query-state";
import { StatusBadge } from "@/components/molecules/status-badge";
import { ActionButton } from "@/components/molecules/action-button";
import { Field } from "@/components/molecules/field";
import { Textarea } from "@/components/atoms/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/atoms/card";
import { DataTable } from "@/components/organisms/data-table";
import { FormDialog } from "@/components/organisms/form-dialog";
export function OrderDetailPage({ id }: { id: string }) {
  const query = useAdminOrderGet(id, { query: { refetchInterval: 30000 } });
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const order = query.data;
  const address = order.fulfillment_snapshot;
  const next =
    order.status === "pending"
      ? { label: "Accept", action: () => adminOrderAccept(id) }
      : order.status === "accepted"
        ? { label: "Start preparing", action: () => adminOrderPrepare(id) }
        : order.status === "preparing"
          ? { label: "Mark ready", action: () => adminOrderReady(id) }
          : order.status === "ready"
            ? { label: "Complete", action: () => adminOrderComplete(id) }
            : null;
  return (
    <>
      <Link href="/orders" className="text-sm text-muted-foreground hover:underline">
        ← Orders
      </Link>
      <PageHeading
        title={`Order #${order.order_number}`}
        description={`${order.customer_name} · ${order.kitchen_name}`}
        action={<StatusBadge value={order.status} />}
      />
      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="flex flex-wrap gap-2">
            {next && <ActionButton label={next.label} action={next.action} />}
            {order.status === "pending" && (
              <FormDialog
                title="Reject order"
                submit={(data) => adminOrderReject(id, { reason: String(data.get("reason")) })}
              >
                <Field id="reject_reason" label="Reason">
                  <Textarea id="reject_reason" name="reason" required maxLength={300} />
                </Field>
              </FormDialog>
            )}
            {["pending", "accepted"].includes(order.status) && (
              <ActionButton
                label="Cancel order"
                action={() => adminOrderCancel(id)}
                description="Cancel this order and release its reserved portions."
              />
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Placed {dateTime(order.created_at)} · Ready {dateTime(order.available_from)}–
            {dateTime(order.available_until)}
          </p>
          {order.customer_note && (
            <div className="rounded-md border p-3">
              <p className="text-sm font-medium">Customer note</p>
              <p className="mt-1 whitespace-pre-wrap text-sm">{order.customer_note}</p>
            </div>
          )}
          {order.rejection_reason && (
            <p className="text-sm">Rejection reason: {order.rejection_reason}</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Items</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <DataTable
            rows={order.items}
            rowKey={(row) => row.menu_listing_id}
            columns={[
              { key: "dish", title: "Dish", render: (row) => row.dish_name },
              {
                key: "quantity",
                title: "Portions",
                render: (row) => row.quantity,
              },
              {
                key: "price",
                title: "Unit price",
                render: (row) => money(row.unit_price_paise),
              },
              {
                key: "total",
                title: "Total",
                render: (row) => money(row.total_paise),
              },
            ]}
          />
          <dl className="ml-auto max-w-xs space-y-2 text-sm">
            <div className="flex justify-between">
              <dt>Subtotal</dt>
              <dd>{money(order.subtotal_paise)}</dd>
            </div>
            <div className="flex justify-between">
              <dt>Delivery</dt>
              <dd>{money(order.delivery_fee_paise)}</dd>
            </div>
            <div className="flex justify-between border-t pt-2 font-semibold">
              <dt>Total</dt>
              <dd>{money(order.total_paise)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {order.fulfillment_type === "pickup" ? "Pickup" : "Home delivery"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p className="font-medium">{address.name ?? address.community_name}</p>
            <p>{[address.zone_name, address.address_label].filter(Boolean).join(" · ")}</p>
            <p className="text-muted-foreground">
              {[address.address, address.city, address.postal_code].filter(Boolean).join(", ")}
            </p>
            {address.instructions && <p className="pt-2">{address.instructions}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Payment acknowledgement</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <StatusBadge value={order.payment_status} />
            <p className="text-sm text-muted-foreground">{order.payment_instructions}</p>
            {order.upi_id && <p className="text-sm">UPI: {order.upi_id}</p>}
            <div className="flex flex-wrap gap-2">
              {["accepted", "preparing", "ready", "completed"].includes(order.status) && (
                <>
                  {order.payment_status === "unpaid" && (
                    <ActionButton
                      label="Record payment reported"
                      action={() => adminOrderReportPayment(id)}
                    />
                  )}
                  {order.payment_status !== "kitchen_confirmed" && (
                    <ActionButton
                      label="Confirm payment"
                      description="Acknowledge that the kitchen received this payment. This does not charge the customer."
                      action={() => adminOrderConfirmPayment(id)}
                    />
                  )}
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Order history</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-3">
            {order.events.map((event, index) => (
              <li
                key={index}
                className="flex flex-wrap justify-between gap-2 border-b pb-3 text-sm last:border-0"
              >
                <div>
                  <StatusBadge value={event.status} />
                  {event.reason && <p className="mt-1 text-muted-foreground">{event.reason}</p>}
                </div>
                <time dateTime={event.created_at} className="text-muted-foreground">
                  {dateTime(event.created_at)}
                </time>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </>
  );
}
