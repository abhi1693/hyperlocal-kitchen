import { UserDeletePage } from "@/components/pages/forms/UserDeletePage";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <UserDeletePage id={(await params).id} />;
}
