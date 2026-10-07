"use client";
import Link from "next/link";
import { useState } from "react";
import type { ReactNode } from "react";
import {
  useAdminOrdersList,
  useAdminFoodKitchens,
  useAdminListMemberships,
} from "@/lib/api/generated/admin";
import type { AdminOrdersListParams, AdminFoodKitchensParams } from "@/lib/api/generated/models";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/atoms/card";
import { QueryState } from "@/components/molecules/query-state";
import { Pagination } from "@/components/molecules/pagination";
import { StatusBadge } from "@/components/molecules/status-badge";
import { DataTable } from "@/components/organisms/data-table";
import { money, dateTime } from "@/lib/utils";

export function RelatedSection({
  title,
  total,
  href,
  children,
}: {
  title: string;
  total?: number;
  href?: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <CardTitle className="text-base">
          {title}
          {total !== undefined && ` (${total})`}
        </CardTitle>
        {href && (
          <Link href={href} className="text-sm underline">
            View full list
          </Link>
        )}
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}
export function RecordLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link className="font-medium hover:underline" href={href}>
      {children}
    </Link>
  );
}
function listHref(path: string, filter: object) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filter))
    if (value != null && value !== "") params.set(key, String(value));
  return `${path}?${params}`;
}
export function RelatedOrders({ filter }: { filter: AdminOrdersListParams }) {
  const [offset, setOffset] = useState(0);
  const query = useAdminOrdersList({ ...filter, limit: 30, offset, sort: "-created_at" });
  return (
    <RelatedSection title="Orders" total={query.data?.total} href={listHref("/orders", filter)}>
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
      {query.data && (
        <>
          <DataTable
            rows={query.data.items}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "order",
                title: "Order",
                render: (row) => (
                  <RecordLink href={`/orders/${row.id}`}>#{row.order_number}</RecordLink>
                ),
              },
              {
                key: "customer",
                title: "Customer",
                render: (row) => (
                  <RecordLink href={`/users/${row.customer_id}`}>{row.customer_name}</RecordLink>
                ),
              },
              {
                key: "kitchen",
                title: "Kitchen",
                render: (row) => (
                  <RecordLink href={`/kitchens/${row.kitchen_id}`}>{row.kitchen_name}</RecordLink>
                ),
              },
              {
                key: "status",
                title: "Status",
                render: (row) => <StatusBadge value={row.status} />,
              },
              {
                key: "payment",
                title: "Payment",
                render: (row) => <StatusBadge value={row.payment_status} />,
              },
              { key: "total", title: "Total", render: (row) => money(row.total_paise) },
              { key: "created", title: "Placed", render: (row) => dateTime(row.created_at) },
            ]}
          />
          <Pagination total={query.data.total} offset={offset} onPage={setOffset} />
        </>
      )}
    </RelatedSection>
  );
}
export function RelatedKitchens({ filter }: { filter: AdminFoodKitchensParams }) {
  const [offset, setOffset] = useState(0);
  const query = useAdminFoodKitchens({ ...filter, limit: 30, offset, sort: "name" });
  return (
    <RelatedSection title="Kitchens" total={query.data?.total} href={listHref("/kitchens", filter)}>
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
      {query.data && (
        <>
          <DataTable
            rows={query.data.items}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "name",
                title: "Kitchen",
                render: (row) => <RecordLink href={`/kitchens/${row.id}`}>{row.name}</RecordLink>,
              },
              {
                key: "community",
                title: "Community",
                render: (row) => (
                  <RecordLink href={`/communities/${row.community_id}`}>
                    {row.community_name}
                  </RecordLink>
                ),
              },
              {
                key: "status",
                title: "Status",
                render: (row) => <StatusBadge value={row.status} />,
              },
            ]}
          />
          <Pagination total={query.data.total} offset={offset} onPage={setOffset} />
        </>
      )}
    </RelatedSection>
  );
}
export function RelatedMemberships({ communityId }: { communityId: string }) {
  const [offset, setOffset] = useState(0);
  const query = useAdminListMemberships({ community_id: communityId, limit: 30, offset });
  return (
    <RelatedSection
      title="Memberships"
      total={query.data?.total}
      href={listHref("/memberships", { community_id: communityId })}
    >
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
      {query.data && (
        <>
          <DataTable
            rows={query.data.items}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "user",
                title: "User",
                render: (row) => (
                  <RecordLink href={`/users/${row.user_id}`}>
                    {row.user_name ?? "Unnamed user"}
                  </RecordLink>
                ),
              },
              {
                key: "home",
                title: "Home",
                render: (row) =>
                  [row.zone_name, row.address_label].filter(Boolean).join(" · ") || "—",
              },
              {
                key: "status",
                title: "Status",
                render: (row) => <StatusBadge value={row.status} />,
              },
            ]}
          />
          <Pagination total={query.data.total} offset={offset} onPage={setOffset} />
        </>
      )}
    </RelatedSection>
  );
}
