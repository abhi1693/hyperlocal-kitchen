import { KitchenEditPage } from "@/components/pages/forms/KitchenEditPage";
export const metadata = { title: "Edit kitchen | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
const values = await params;
return <KitchenEditPage id={values.id} />;
}
