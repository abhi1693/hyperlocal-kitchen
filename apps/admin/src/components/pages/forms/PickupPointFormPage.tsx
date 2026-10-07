"use client";
import {
  useAdminGetCommunity,
  useCommunityPickupPointsApiV1CommunitiesCommunityIdPickupPointsGet,
  createPickupPointApiV1CommunitiesCommunityIdPickupPointsPost,
  editPickupPointApiV1PickupPointsPointIdPatch,
} from "@/lib/api/generated/admin";
import { Field } from "@/components/molecules/field";
import { QueryState } from "@/components/molecules/query-state";
import { Input } from "@/components/atoms/input";
import { Combobox } from "@/components/molecules/combobox";
import { Textarea } from "@/components/atoms/textarea";
import { ResourceForm } from "@/components/organisms/resource-form";

export function PickupPointFormPage({ id, pointId }: { id: string; pointId?: string }) {
  const points = useCommunityPickupPointsApiV1CommunitiesCommunityIdPickupPointsGet(id);
  const query = useAdminGetCommunity(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const community = query.data;
  if (!points.data)
    return (
      <QueryState pending={points.isPending} error={points.error} retry={() => points.refetch()} />
    );
  const row = points.data.find((point) => point.id === pointId);
  if (pointId && !row) return <p role="alert">Pickup point not found in this community.</p>;
  return (
    <ResourceForm
      create={!row}
      cancelHref={`/communities/${id}`}
      title={row ? "Edit pickup point" : "New pickup point"}
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
        <Combobox
          label="Zone"
          id="point_zone"
          name="zone_id"
          defaultValue={row?.zone_id ?? ""}
          options={[
            { value: "", label: "None" },
            ...community.zones
              .filter((zone) => zone.active)
              .map((zone) => ({ value: zone.id, label: zone.name })),
          ]}
        />
      </Field>
      <Field label="Instructions" id="point_instructions">
        <Textarea
          id="point_instructions"
          name="instructions"
          maxLength={1000}
          defaultValue={row?.instructions ?? ""}
        />
      </Field>
    </ResourceForm>
  );
}
