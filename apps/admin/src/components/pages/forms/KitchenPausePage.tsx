"use client";
import { useAdminFoodKitchen, adminFoodPauseKitchen } from "@/lib/api/generated/admin";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Textarea } from "@/components/atoms/textarea";
import { ResourceForm } from "@/components/organisms/resource-form";

export function KitchenPausePage({ id }: { id: string }) {
  const query = useAdminFoodKitchen(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const kitchen = query.data;
  return (
    <ResourceForm
      cancelHref={`/kitchens/${id}`}
      title="Pause orders"
      description="Existing orders will not be affected."
      submit={(data) =>
        adminFoodPauseKitchen(id, {
          reason: String(data.get("reason") ?? "") || null,
        })
      }
    >
      <Field label="Reason (optional)" id="pause_reason">
        <Textarea id="pause_reason" name="reason" maxLength={500} />
      </Field>
    </ResourceForm>
  );
}
