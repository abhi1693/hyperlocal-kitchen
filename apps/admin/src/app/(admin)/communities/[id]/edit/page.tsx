import { CommunityFormPage } from "@/components/pages/forms/CommunityFormPage";
export const metadata = { title: "Edit communitie | Kitchen Admin" };
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
const values = await params;
return <CommunityFormPage id={values.id} />;
}
