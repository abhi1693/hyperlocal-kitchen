import { MembershipsPage } from "@/components/pages/memberships-page";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ community_id?: string; user_id?: string }>;
}) {
  const query = await searchParams;
  return <MembershipsPage initialCommunity={query.community_id} initialUser={query.user_id} />;
}
