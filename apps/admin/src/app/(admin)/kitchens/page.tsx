import { KitchensPage } from "@/components/pages/kitchens-page";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  return (
    <KitchensPage
      initialStatus={
        status === "pending" || status === "approved" || status === "suspended" ? status : ""
      }
    />
  );
}
