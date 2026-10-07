import { OrdersPage } from "@/components/pages/orders-page";
import { AdminOrdersListStatus } from "@/lib/api/generated/models";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const valid = Object.values(AdminOrdersListStatus).find((value) => value === status);
  return <OrdersPage initialStatus={valid ?? ""} />;
}
