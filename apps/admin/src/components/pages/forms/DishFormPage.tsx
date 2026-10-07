"use client";
import {
  useAdminFoodKitchen,
  adminFoodCreateKitchenDish,
  adminFoodUpdateDish,
} from "@/lib/api/generated/admin";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { Textarea } from "@/components/atoms/textarea";
import { ResourceForm } from "@/components/organisms/resource-form";
import { useAdminFoodDish } from "@/lib/api/generated/admin";

export function DishFormPage({ id, dishId }: { id: string; dishId?: string }) {
  const query = useAdminFoodDish(dishId ?? "", { query: { enabled: !!dishId } });
  const kitchenQuery = useAdminFoodKitchen(id);
  if (!kitchenQuery.data)
    return (
      <QueryState
        pending={kitchenQuery.isPending}
        error={kitchenQuery.error}
        retry={() => kitchenQuery.refetch()}
      />
    );
  const kitchen = kitchenQuery.data;
  if (dishId && !query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const row = dishId ? query.data : undefined;
  if (row && row.kitchen_id !== id) return <p role="alert">Dish not found in this kitchen.</p>;
  return (
    <ResourceForm
      create={!row}
      cancelHref={`/kitchens/${id}`}
      title={row ? "Edit dish" : "New dish"}
      submit={(data) => {
        const payload = {
          name: String(data.get("name")),
          description: String(data.get("description") ?? "") || null,
          image_url: String(data.get("image_url") ?? "") || null,
        };
        return row ? adminFoodUpdateDish(row.id, payload) : adminFoodCreateKitchenDish(id, payload);
      }}
    >
      <Field label="Dish name" id="dish_name">
        <Input id="dish_name" name="name" required maxLength={150} defaultValue={row?.name} />
      </Field>
      <Field label="Description" id="dish_description">
        <Textarea
          id="dish_description"
          name="description"
          maxLength={1000}
          defaultValue={row?.description ?? ""}
        />
      </Field>
      <Field label="Photo URL" id="dish_photo">
        <Input
          id="dish_photo"
          name="image_url"
          type="url"
          placeholder="https://…"
          maxLength={2048}
          defaultValue={row?.image_url ?? ""}
        />
      </Field>
    </ResourceForm>
  );
}
