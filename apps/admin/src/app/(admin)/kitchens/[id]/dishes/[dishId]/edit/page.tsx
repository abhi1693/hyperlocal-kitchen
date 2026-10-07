import { DishFormPage } from "@/components/pages/forms/DishFormPage";
export const metadata = { title: "Edit dish | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string; dishId: string }> }) {
const values = await params;
return <DishFormPage id={values.id} dishId={values.dishId} />;
}
