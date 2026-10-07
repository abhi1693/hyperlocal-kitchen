import { KitchenApprovePage } from "@/components/pages/forms/KitchenApprovePage";
export const metadata = { title: "Approve kitchen | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
const values = await params;
return <KitchenApprovePage id={values.id} />;
}
