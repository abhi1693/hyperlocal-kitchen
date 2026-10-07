import { KitchenDetailPage } from "@/components/pages/kitchen-detail-page";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <KitchenDetailPage id={(await params).id} />;
}
