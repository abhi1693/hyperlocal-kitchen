"use client";
import { useAdminGetCommunity, adminCreateZone, adminUpdateZone } from "@/lib/api/generated/admin";
import { CommunityZoneCreateZoneType } from "@/lib/api/generated/models";
import { Field } from "@/components/molecules/field";
import { QueryState } from "@/components/molecules/query-state";
import { Input } from "@/components/atoms/input";
import { Combobox } from "@/components/molecules/combobox";
import { ResourceForm } from "@/components/organisms/resource-form";

export function ZoneFormPage({ id, zoneId }: { id: string; zoneId?: string }) {
  const query = useAdminGetCommunity(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const community = query.data;
  const row = community.zones.find((zone) => zone.id === zoneId);
  if (zoneId && !row) return <p role="alert">Zone not found in this community.</p>;
  return (
    <ResourceForm
      create={!row}
      cancelHref={`/communities/${id}`}
      title={row ? "Edit zone" : "New zone"}
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
        <Combobox
          label="Type"
          id="zone_type"
          name="zone_type"
          defaultValue={row?.zone_type ?? "other"}
          options={Object.values(CommunityZoneCreateZoneType).map((value) => ({
            value,
            label: value[0].toUpperCase() + value.slice(1),
          }))}
        />
      </Field>
      <Field label="Parent zone" id="parent_zone_id">
        <Combobox
          label="Parent zone"
          id="parent_zone_id"
          name="parent_zone_id"
          defaultValue={row?.parent_zone_id ?? ""}
          options={[
            { value: "", label: "None" },
            ...community.zones
              .filter((zone) => zone.id !== row?.id)
              .map((zone) => ({ value: zone.id, label: zone.name })),
          ]}
        />
      </Field>
    </ResourceForm>
  );
}
