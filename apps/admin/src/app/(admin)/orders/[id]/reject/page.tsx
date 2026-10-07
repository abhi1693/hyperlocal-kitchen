import { OrderActionPage } from "@/components/pages/forms/OrderActionPage";
export const metadata = { title: "Reject order | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <OrderActionPage id={(await params).id} action="reject" />;
}
