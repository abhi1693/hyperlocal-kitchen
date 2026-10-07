import { CommunityDetailPage } from "@/components/pages/community-detail-page";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <CommunityDetailPage id={(await params).id} />;
}
