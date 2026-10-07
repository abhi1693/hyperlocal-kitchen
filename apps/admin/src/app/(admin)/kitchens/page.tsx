import { KitchensPage } from "@/components/pages/kitchens-page";
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
  return (
    <KitchensPage
      initialCommunity={community_id}
      userId={user_id}
      initialStatus={
        status === "pending" || status === "approved" || status === "suspended" ? status : ""
      }
    />
  );
}
