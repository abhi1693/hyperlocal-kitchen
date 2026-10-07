import type { OrderOut } from "@/lib/api/generated/models";
export type OrderAction =
  | "accept"
  | "reject"
  | "prepare"
  | "ready"
  | "complete"
  | "cancel"
  | "report-payment"
  | "confirm-payment";
export const orderActionLabels: Record<OrderAction, string> = {
  accept: "Accept order",
  reject: "Reject order",
  prepare: "Start preparing",
  ready: "Mark ready",
  complete: "Complete order",
  cancel: "Cancel order",
  "report-payment": "Record payment reported",
  "confirm-payment": "Confirm payment",
};
export function availableOrderActions(order: OrderOut): OrderAction[] {
  const actions: OrderAction[] = [];
  if (order.status === "pending") actions.push("accept", "reject", "cancel");
  if (order.status === "accepted") actions.push("prepare", "cancel");
  if (order.status === "preparing") actions.push("ready");
  if (order.status === "ready") actions.push("complete");
  if (["accepted", "preparing", "ready", "completed"].includes(order.status)) {
    if (order.payment_status === "unpaid") actions.push("report-payment");
    if (order.payment_status !== "kitchen_confirmed") actions.push("confirm-payment");
  }
  return actions;
}
