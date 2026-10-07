import { Badge } from "@/components/atoms/badge";

type StatusTone = "success" | "warning" | "info" | "danger" | "neutral";
const statusTones: Record<string, StatusTone> = {
  active: "success",
  approved: "success",
  accepting: "success",
  accepting_orders: "success",
  published: "success",
  ready: "success",
  completed: "success",
  kitchen_confirmed: "success",
  pending: "warning",
  paused: "warning",
  unpaid: "warning",
  sold_out: "warning",
  accepted: "info",
  preparing: "info",
  customer_reported: "info",
  owner: "info",
  manager: "info",
  suspended: "danger",
  rejected: "danger",
  cancelled: "danger",
  inactive: "neutral",
  archived: "neutral",
  expired: "neutral",
  draft: "neutral",
};

export function StatusBadge({ value }: { value: string }) {
  const status = value.trim().toLowerCase().replaceAll(" ", "_");
  return (
    <Badge variant={statusTones[status] ?? "neutral"} className="capitalize">
      {value.replaceAll("_", " ")}
    </Badge>
  );
}
