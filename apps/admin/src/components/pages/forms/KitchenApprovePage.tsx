"use client";
import { useAdminFoodKitchen, adminFoodApproveKitchen } from "@/lib/api/generated/admin";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { ResourceForm } from "@/components/organisms/resource-form";

export function KitchenApprovePage({ id }: { id: string }) {
  const query = useAdminFoodKitchen(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const kitchen = query.data;
  return (
    <ResourceForm
      cancelHref={`/kitchens/${id}`}
      title="Approve kitchen"
      submit={(data) =>
        adminFoodApproveKitchen(id, {
          fssai_number: String(data.get("fssai_number")),
        })
      }
    >
      <Field label="FSSAI number" id="fssai_number">
        <Input
          id="fssai_number"
          name="fssai_number"
          inputMode="numeric"
          pattern="[0-9]{14}"
          maxLength={14}
          required
          defaultValue={kitchen.fssai_number ?? ""}
        />
      </Field>
    </ResourceForm>
  );
}
