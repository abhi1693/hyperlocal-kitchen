import { PickupPointFormPage } from "@/components/pages/forms/PickupPointFormPage";
export const metadata = { title: "Edit pickup point | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string; pointId: string }> }) {
const values = await params;
return <PickupPointFormPage id={values.id} pointId={values.pointId} />;
}
