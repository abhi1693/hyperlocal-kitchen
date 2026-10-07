import { ZoneFormPage } from "@/components/pages/forms/ZoneFormPage";
export const metadata = { title: "New zone | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
const values = await params;
return <ZoneFormPage id={values.id} />;
}
