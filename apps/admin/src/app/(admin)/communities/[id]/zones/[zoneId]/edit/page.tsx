import { ZoneFormPage } from "@/components/pages/forms/ZoneFormPage";
export const metadata = { title: "Edit zone | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string; zoneId: string }> }) {
const values = await params;
return <ZoneFormPage id={values.id} zoneId={values.zoneId} />;
}
