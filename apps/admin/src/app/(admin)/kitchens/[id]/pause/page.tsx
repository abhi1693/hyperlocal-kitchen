import { KitchenPausePage } from "@/components/pages/forms/KitchenPausePage";
export const metadata = { title: "Pause orders | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
const values = await params;
return <KitchenPausePage id={values.id} />;
}
