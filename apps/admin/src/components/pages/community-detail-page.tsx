"use client";
import Link from "next/link";
import {
  RelatedOrders,
  RelatedKitchens,
  RelatedMemberships,
} from "@/components/organisms/related-records";
import { communityTypeLabels } from "@/lib/api/community-type-choices";
import {
  useAdminGetCommunity,
  useCommunityPickupPointsApiV1CommunitiesCommunityIdPickupPointsGet,
  adminUpdateZone,
  editPickupPointApiV1PickupPointsPointIdPatch,
} from "@/lib/api/generated/admin";
import { PageHeading } from "@/components/molecules/page-heading";
import { QueryState } from "@/components/molecules/query-state";
import { StatusBadge } from "@/components/molecules/status-badge";
import { ActionButton } from "@/components/molecules/action-button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/atoms/card";
import { DataTable } from "@/components/organisms/data-table";
import { FormLink } from "@/components/molecules/form-link";
export function CommunityDetailPage({ id }: { id: string }) {
  const query = useAdminGetCommunity(id);
  const points = useCommunityPickupPointsApiV1CommunitiesCommunityIdPickupPointsGet(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const community = query.data;
  return (
    <>
      <Link href="/communities" className="text-sm text-muted-foreground hover:underline">
        ← Communities
      </Link>
      <PageHeading
        title={community.name}
        description={`${community.city} · ${communityTypeLabels[community.type]}`}
        action={<StatusBadge value={community.status} />}
      />
      <Card>
        <CardContent className="pt-6 text-sm">
          <p>{community.address ?? "No community address"}</p>
          <p className="text-muted-foreground">{community.postal_code}</p>
          <Link className="mt-3 inline-block underline" href={`/memberships?community_id=${id}`}>
            Manage memberships
          </Link>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Zones ({community.zones.length})</CardTitle>
          <FormLink href={`/communities/${id}/zones/new`}>New zone</FormLink>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={community.zones}
            rowKey={(row) => row.id}
            columns={[
              { key: "name", title: "Zone", render: (row) => row.name },
              { key: "type", title: "Type", render: (row) => row.zone_type },
              {
                key: "parent",
                title: "Parent",
                render: (row) =>
                  community.zones.find((zone) => zone.id === row.parent_zone_id)?.name ?? "—",
              },
              {
                key: "active",
                title: "Status",
                render: (row) => <StatusBadge value={row.active ? "active" : "inactive"} />,
              },
              {
                key: "actions",
                title: "Actions",
                render: (row) => (
                  <div className="flex gap-2">
                    <FormLink href={`/communities/${id}/zones/${row.id}/edit`}>Edit</FormLink>
                    <ActionButton
                      label={row.active ? "Deactivate" : "Activate"}
                      action={() => adminUpdateZone(row.id, { active: !row.active })}
                    />
                  </div>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            Pickup points{points.data && ` (${points.data.length})`}
          </CardTitle>
          <FormLink href={`/communities/${id}/pickup-points/new`}>New pickup point</FormLink>
        </CardHeader>
        <CardContent>
          <QueryState
            pending={points.isPending}
            error={points.error}
            retry={() => points.refetch()}
          />
          {points.data && (
            <DataTable
              rows={points.data}
              rowKey={(row) => row.id}
              columns={[
                { key: "name", title: "Point", render: (row) => row.name },
                {
                  key: "address",
                  title: "Collection address",
                  render: (row) => row.address_label,
                },
                {
                  key: "scope",
                  title: "Scope",
                  render: (row) => (row.kitchen_id ? "Kitchen" : "Shared"),
                },
                {
                  key: "status",
                  title: "Status",
                  render: (row) => <StatusBadge value={row.active ? "active" : "inactive"} />,
                },
                {
                  key: "actions",
                  title: "Actions",
                  render: (row) => (
                    <div className="flex gap-2">
                      <FormLink href={`/communities/${id}/pickup-points/${row.id}/edit`}>
                        Edit
                      </FormLink>
                      <ActionButton
                        label={row.active ? "Deactivate" : "Activate"}
                        action={() =>
                          editPickupPointApiV1PickupPointsPointIdPatch(row.id, {
                            active: !row.active,
                          })
                        }
                      />
                    </div>
                  ),
                },
              ]}
            />
          )}
        </CardContent>
      </Card>
      <RelatedMemberships communityId={id} />
      <RelatedKitchens filter={{ community_id: id }} />
      <RelatedOrders filter={{ community_id: id }} />
    </>
  );
}
