import { ListingCreatePage } from "@/components/pages/forms/ListingCreatePage";
export const metadata = {title: "Publish listing | Kitchen Admin"};
export default async function Page({params, searchParams}: {params: Promise<{id: string}>; searchParams: Promise<{dish_id?: string; date?: string}>}) {
 const {id} = await params; const query = await searchParams;
 return <ListingCreatePage id={id} dishId={query.dish_id} date={query.date} />;
}
