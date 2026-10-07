"use client";
import { useAdminFoodKitchen, adminFoodCreateKitchenMember } from "@/lib/api/generated/admin";
import type { KitchenMemberCreateRole } from "@/lib/api/generated/models";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Combobox } from "@/components/molecules/combobox";
import { ResourceForm } from "@/components/organisms/resource-form";

export function KitchenOperatorPage({ id }: { id: string }) {
  const query = useAdminFoodKitchen(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const kitchen = query.data;
  return (
    <ResourceForm
      create
      cancelHref={`/kitchens/${id}`}
      title="Add operator"
      submit={(data) =>
        adminFoodCreateKitchenMember(id, {
          user_id: String(data.get("user_id")),
          role: String(data.get("role")) as KitchenMemberCreateRole,
        })
      }
    >
      <ReferencePicker
        kind="user"
        name="user_id"
        label="Resident"
        communityId={kitchen.community_id}
      />
      <Field label="Role" id="operator_role">
        <Combobox
          label="Role"
          id="operator_role"
          name="role"
          options={[
            { value: "manager", label: "Manager" },
            { value: "owner", label: "Owner" },
          ]}
        />
      </Field>
    </ResourceForm>
  );
}
