import { OrdersPage } from "@/components/pages/orders-page";
import { AdminOrdersListStatus } from "@/lib/api/generated/models";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{
    status?: string;
    community_id?: string;
    customer_id?: string;
    kitchen_id?: string;
    user_id?: string;
  }>;
}) {
  const { status, community_id, customer_id, kitchen_id, user_id } = await searchParams;
  const valid = Object.values(AdminOrdersListStatus).find((value) => value === status);
  return (
    <OrdersPage
      initialCommunity={community_id}
      customerId={customer_id}
      kitchenId={kitchen_id}
      initialStatus={valid ?? ""}
    />
  );
}
