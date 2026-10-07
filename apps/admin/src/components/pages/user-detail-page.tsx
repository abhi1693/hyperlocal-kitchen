"use client";
import Link from "next/link";
import { RelatedOrders, RelatedKitchens } from "@/components/organisms/related-records";
import { useState } from "react";
import { useAdminGetUser, useAdminListMemberships } from "@/lib/api/generated/admin";
import { dateTime } from "@/lib/utils";
import { PageHeading } from "@/components/molecules/page-heading";
import { QueryState } from "@/components/molecules/query-state";
import { StatusBadge } from "@/components/molecules/status-badge";
import { Pagination } from "@/components/molecules/pagination";
import { FormLink } from "@/components/molecules/form-link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/atoms/card";
import { DataTable } from "@/components/organisms/data-table";

export function UserDetailPage({ id }: { id: string }) {
  const [offset, setOffset] = useState(0);
  const user = useAdminGetUser(id);
  const memberships = useAdminListMemberships(
    { user_id: id, limit: 30, offset },
    { query: { enabled: !!user.data } },
  );
  if (!user.data)
    return <QueryState pending={user.isPending} error={user.error} retry={() => user.refetch()} />;
  const row = user.data;
  return (
    <>
      <nav aria-label="Breadcrumb" className="flex flex-wrap gap-2 text-sm text-muted-foreground">
        <Link href="/users" className="hover:underline">
          Users
        </Link>
        <span aria-hidden>/</span>
        <span aria-current="page">{row.name ?? "Unnamed user"}</span>
      </nav>
      <PageHeading
        title={row.name ?? "Unnamed user"}
        description="Account profile and community access."
        action={
          <div className="flex flex-wrap gap-2">
            <FormLink href={`/users/${id}/edit`}>Edit user</FormLink>
            <FormLink href={`/users/${id}/delete`}>Delete user</FormLink>
            <FormLink href={`/users/${id}/${row.is_active ? "deactivate" : "activate"}`}>
              {row.is_active ? "Deactivate user" : "Activate user"}
            </FormLink>
          </div>
        }
      />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-6 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Name</dt>
              <dd className="mt-1">{row.name ?? "Not provided"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Contact phone</dt>
              <dd className="mt-1">{row.phone ?? "Not provided"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Account status</dt>
              <dd className="mt-1">
                <StatusBadge value={row.is_active ? "active" : "inactive"} />
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Joined</dt>
              <dd className="mt-1">{dateTime(row.created_at)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Community memberships{memberships.data && ` (${memberships.data.total})`}
          </CardTitle>
          <Link href={`/memberships?user_id=${id}`} className="text-sm underline">
            View full list
          </Link>
        </CardHeader>
        <CardContent className="space-y-4">
          <QueryState
            pending={memberships.isPending}
            error={memberships.error}
            retry={() => memberships.refetch()}
          />
          {memberships.data && (
            <>
              <DataTable
                rows={memberships.data.items}
                rowKey={(member) => member.id}
                empty="This user has no community memberships."
                columns={[
                  {
                    key: "community",
                    title: "Community",
                    render: (member) => (
                      <Link
                        href={`/communities/${member.community_id}`}
                        className="font-medium hover:underline"
                      >
                        {member.community_name}
                      </Link>
                    ),
                  },
                  {
                    key: "home",
                    title: "Home",
                    render: (member) =>
                      [member.zone_name, member.address_label].filter(Boolean).join(" · ") || "—",
                  },
                  {
                    key: "status",
                    title: "Status",
                    render: (member) => <StatusBadge value={member.status} />,
                  },
                  {
                    key: "actions",
                    title: "Actions",
                    render: (member) => (
                      <FormLink
                        href={`/memberships?community_id=${member.community_id}&user_id=${id}`}
                      >
                        Manage membership
                      </FormLink>
                    ),
                  },
                ]}
              />
              <Pagination total={memberships.data.total} offset={offset} onPage={setOffset} />
            </>
          )}
        </CardContent>
      </Card>
      <RelatedKitchens filter={{ user_id: id }} />
      <RelatedOrders filter={{ customer_id: id }} />
    </>
  );
}
