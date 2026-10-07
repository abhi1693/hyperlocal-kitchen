import { KitchenOperatorPage } from "@/components/pages/forms/KitchenOperatorPage";
export const metadata = { title: "New operator | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
const values = await params;
return <KitchenOperatorPage id={values.id} />;
}
