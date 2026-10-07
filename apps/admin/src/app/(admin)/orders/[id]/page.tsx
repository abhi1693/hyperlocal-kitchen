import { OrderDetailPage } from "@/components/pages/order-detail-page";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <OrderDetailPage id={(await params).id} />;
}
