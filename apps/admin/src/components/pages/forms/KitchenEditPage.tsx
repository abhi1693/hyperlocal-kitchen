"use client";
import { useAdminFoodKitchen, adminFoodUpdateKitchen } from "@/lib/api/generated/admin";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { Textarea } from "@/components/atoms/textarea";
import { ResourceForm } from "@/components/organisms/resource-form";

export function KitchenEditPage({ id }: { id: string }) {
  const query = useAdminFoodKitchen(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const kitchen = query.data;
  return (
    <ResourceForm
      cancelHref={`/kitchens/${id}`}
      title="Edit kitchen"
      submit={(data) =>
        adminFoodUpdateKitchen(id, {
          name: String(data.get("name")),
          description: String(data.get("description") ?? "") || null,
          address_label: String(data.get("address_label") ?? "") || null,
          upi_id: String(data.get("upi_id") ?? "") || null,
          pickup_enabled: data.has("pickup_enabled"),
          delivery_enabled: data.has("delivery_enabled"),
          delivery_fee_paise: Math.round(Number(data.get("delivery_fee")) * 100),
        })
      }
    >
      <Field label="Name" id="edit_kitchen_name">
        <Input
          id="edit_kitchen_name"
          name="name"
          required
          maxLength={150}
          defaultValue={kitchen.name}
        />
      </Field>
      <Field label="Description" id="edit_description">
        <Textarea
          id="edit_description"
          name="description"
          maxLength={1000}
          defaultValue={kitchen.description ?? ""}
        />
      </Field>
      <Field label="Kitchen address" id="edit_address">
        <Input
          id="edit_address"
          name="address_label"
          maxLength={250}
          defaultValue={kitchen.address_label ?? ""}
        />
      </Field>
      <Field label="UPI ID" id="edit_upi">
        <Input id="edit_upi" name="upi_id" maxLength={150} defaultValue={kitchen.upi_id ?? ""} />
      </Field>
      <div className="flex gap-6">
        <label className="flex items-center gap-2 text-sm">
          <Input type="checkbox" name="pickup_enabled" defaultChecked={kitchen.pickup_enabled} />
          Pickup
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Input
            type="checkbox"
            name="delivery_enabled"
            defaultChecked={kitchen.delivery_enabled}
          />
          Delivery
        </label>
      </div>
      <Field label="Delivery fee (₹)" id="edit_delivery_fee">
        <Input
          id="edit_delivery_fee"
          name="delivery_fee"
          type="number"
          min="0"
          max="10000"
          step="0.01"
          defaultValue={kitchen.delivery_fee_paise / 100}
        />
      </Field>
    </ResourceForm>
  );
}
