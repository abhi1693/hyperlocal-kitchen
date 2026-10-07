"use client";
import { adminCreateCommunity, adminUpdateCommunity } from "@/lib/api/generated/admin";
import { type CommunityType } from "@/lib/api/generated/models";
import { communityTypeChoices } from "@/lib/api/community-type-choices";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { Combobox } from "@/components/molecules/combobox";
import { ResourceForm } from "@/components/organisms/resource-form";
import { useAdminGetCommunity } from "@/lib/api/generated/admin";

export function CommunityFormPage({ id }: { id?: string }) {
  const query = useAdminGetCommunity(id ?? "", { query: { enabled: !!id } });
  if (id && !query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const row = id ? query.data : undefined;
  return (
    <ResourceForm
      create={!row}
      cancelHref={id ? `/communities/${id}` : "/communities"}
      title={row ? "Edit community" : "New community"}
      submit={(data) => {
        const payload = {
          name: String(data.get("name")),
          city: String(data.get("city")),
          type: String(data.get("type")) as CommunityType,
          address: String(data.get("address") ?? "") || null,
          postal_code: String(data.get("postal_code") ?? "") || null,
        };
        return row ? adminUpdateCommunity(row.id, payload) : adminCreateCommunity(payload);
      }}
    >
      <Field id="name" label="Name">
        <Input id="name" name="name" required maxLength={200} defaultValue={row?.name} />
      </Field>
      <Field id="type" label="Community type">
        <Combobox
          label="Community type"
          id="type"
          name="type"
          defaultValue={row?.type ?? "residential_society"}
          options={communityTypeChoices.map(({ slug, label }) => ({ value: slug, label }))}
        />
      </Field>
      <Field id="city" label="City">
        <Input id="city" name="city" required maxLength={100} defaultValue={row?.city} />
      </Field>
      <Field id="address" label="Address">
        <Input id="address" name="address" maxLength={500} defaultValue={row?.address ?? ""} />
      </Field>
      <Field id="postal_code" label="Postal code">
        <Input
          id="postal_code"
          name="postal_code"
          maxLength={20}
          defaultValue={row?.postal_code ?? ""}
        />
      </Field>
    </ResourceForm>
  );
}
