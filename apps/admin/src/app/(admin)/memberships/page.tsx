import { MembershipsPage } from "@/components/pages/memberships-page";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ community_id?: string }>;
}) {
  return <MembershipsPage initialCommunity={(await searchParams).community_id} />;
}
