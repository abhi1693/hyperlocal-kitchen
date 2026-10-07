import { UserDetailPage } from "@/components/pages/user-detail-page";
export const metadata = { title: "User details | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <UserDetailPage id={(await params).id} />;
}
