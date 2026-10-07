"use client";
import Link from "next/link";
import {
  useAdminGetCommunity,
  useCommunityPickupPointsApiV1CommunitiesCommunityIdPickupPointsGet,
  adminCreateZone,
  adminUpdateZone,
  createPickupPointApiV1CommunitiesCommunityIdPickupPointsPost,
  editPickupPointApiV1PickupPointsPointIdPatch,
} from "@/lib/api/generated/admin";
import {
  CommunityZoneCreateZoneType,
  type CommunityZoneOut,
  type PickupPointOut,
} from "@/lib/api/generated/models";
import { PageHeading } from "@/components/molecules/page-heading";
import { Field } from "@/components/molecules/field";
import { QueryState } from "@/components/molecules/query-state";
import { StatusBadge } from "@/components/molecules/status-badge";
import { ActionButton } from "@/components/molecules/action-button";
import { Input } from "@/components/atoms/input";
import { Select } from "@/components/atoms/select";
import { Textarea } from "@/components/atoms/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/atoms/card";
import { DataTable } from "@/components/organisms/data-table";
import { FormDialog } from "@/components/organisms/form-dialog";
export function CommunityDetailPage({ id }: { id: string }) {
  const query = useAdminGetCommunity(id);
  const points = useCommunityPickupPointsApiV1CommunitiesCommunityIdPickupPointsGet(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const community = query.data;
  function zoneForm(row?: CommunityZoneOut) {
    return (
      <FormDialog
        title={row ? "Edit zone" : "New zone"}
        label={row ? "Edit" : "New zone"}
        submit={(data) => {
          const payload = {
            name: String(data.get("name")),
            zone_type: String(data.get("zone_type")) as CommunityZoneCreateZoneType,
            parent_zone_id: String(data.get("parent_zone_id") ?? "") || null,
          };
          return row ? adminUpdateZone(row.id, payload) : adminCreateZone(id, payload);
        }}
      >
        <Field label="Name" id="zone_name">
          <Input id="zone_name" name="name" required maxLength={100} defaultValue={row?.name} />
        </Field>
        <Field label="Type" id="zone_type">
          <Select id="zone_type" name="zone_type" defaultValue={row?.zone_type ?? "other"}>
            {Object.values(CommunityZoneCreateZoneType).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Parent zone" id="parent_zone_id">
          <Select
            id="parent_zone_id"
            name="parent_zone_id"
            defaultValue={row?.parent_zone_id ?? ""}
          >
            <option value="">None</option>
            {community.zones
              .filter((zone) => zone.id !== row?.id)
              .map((zone) => (
                <option key={zone.id} value={zone.id}>
                  {zone.name}
                </option>
              ))}
          </Select>
        </Field>
      </FormDialog>
    );
  }
  function pointForm(row?: PickupPointOut) {
    return (
      <FormDialog
        title={row ? "Edit pickup point" : "New pickup point"}
        label={row ? "Edit" : "New pickup point"}
        submit={(data) => {
          const payload = {
            name: String(data.get("name")),
            address_label: String(data.get("address_label")),
            zone_id: String(data.get("zone_id") ?? "") || null,
            instructions: String(data.get("instructions") ?? "") || null,
          };
          return row
            ? editPickupPointApiV1PickupPointsPointIdPatch(row.id, payload)
            : createPickupPointApiV1CommunitiesCommunityIdPickupPointsPost(id, payload);
        }}
      >
        <Field label="Name" id="point_name">
          <Input id="point_name" name="name" required maxLength={150} defaultValue={row?.name} />
        </Field>
        <Field label="Collection address" id="point_address">
          <Input
            id="point_address"
            name="address_label"
            required
            maxLength={250}
            defaultValue={row?.address_label}
          />
        </Field>
        <Field label="Zone" id="point_zone">
          <Select id="point_zone" name="zone_id" defaultValue={row?.zone_id ?? ""}>
            <option value="">None</option>
            {community.zones
              .filter((zone) => zone.active)
              .map((zone) => (
                <option key={zone.id} value={zone.id}>
                  {zone.name}
                </option>
              ))}
          </Select>
        </Field>
        <Field label="Instructions" id="point_instructions">
          <Textarea
            id="point_instructions"
            name="instructions"
            maxLength={1000}
            defaultValue={row?.instructions ?? ""}
          />
        </Field>
      </FormDialog>
    );
  }
  return (
    <>
      <Link href="/communities" className="text-sm text-muted-foreground hover:underline">
        ← Communities
      </Link>
      <PageHeading
        title={community.name}
        description={`${community.city} · ${community.type.replaceAll("_", " ")}`}
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
          <CardTitle className="text-base">Zones</CardTitle>
          {zoneForm()}
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
                    {zoneForm(row)}
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
          <CardTitle className="text-base">Pickup points</CardTitle>
          {pointForm()}
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
                      {pointForm(row)}
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
    </>
  );
}
