"use client";
import Link from "next/link";
import {
  useAdminListCommunities,
  useAdminFoodKitchens,
  useAdminOrdersList,
} from "@/lib/api/generated/admin";
import { PageHeading } from "@/components/molecules/page-heading";
import { QueryState } from "@/components/molecules/query-state";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/atoms/card";
export function OverviewPage() {
  const communities = useAdminListCommunities({ limit: 1 });
  const kitchens = useAdminFoodKitchens({ limit: 1, status: "pending" });
  const orders = useAdminOrdersList({ limit: 1, status: "pending" });
  return (
    <>
      <PageHeading
        title="Overview"
        description="Manage communities, approve kitchens, and support orders."
      />
      <QueryState
        pending={communities.isPending || kitchens.isPending || orders.isPending}
        error={communities.error ?? kitchens.error ?? orders.error}
        retry={() => {
          communities.refetch();
          kitchens.refetch();
          orders.refetch();
        }}
      />
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          {
            title: "Communities",
            count: communities.data?.total,
            href: "/communities",
          },
          {
            title: "Kitchens awaiting approval",
            count: kitchens.data?.total,
            href: "/kitchens?status=pending",
          },
          {
            title: "Pending orders",
            count: orders.data?.total,
            href: "/orders?status=pending",
          },
        ].map((item) => (
          <Link href={item.href} key={item.title}>
            <Card className="h-full hover:bg-muted/40">
              <CardHeader>
                <CardTitle className="text-sm font-medium">{item.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-semibold">{item.count ?? "—"}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Get your first kitchen ready</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            Create and activate a community, add resident memberships, then create and approve a
            kitchen.
          </p>
          <p>
            Use the order screen to follow the kitchen’s first orders through preparation and
            completion.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
