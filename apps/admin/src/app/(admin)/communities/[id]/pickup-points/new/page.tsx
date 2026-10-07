import { PickupPointFormPage } from "@/components/pages/forms/PickupPointFormPage";
export const metadata = { title: "New pickup point | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
const values = await params;
return <PickupPointFormPage id={values.id} />;
}
