import { UserStatusPage } from "@/components/pages/forms/UserStatusPage";
export const metadata = { title: "Deactivate user | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <UserStatusPage id={(await params).id} active={false} />;
}
