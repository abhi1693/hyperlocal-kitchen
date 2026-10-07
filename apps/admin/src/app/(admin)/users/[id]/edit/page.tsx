import { UserEditPage } from "@/components/pages/forms/UserEditPage";
export const metadata = { title: "Edit user | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const values = await params;
  return <UserEditPage id={values.id} />;
}
