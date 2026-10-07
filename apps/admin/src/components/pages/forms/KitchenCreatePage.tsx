"use client";
import { useState } from "react";
import { adminFoodCreateKitchen } from "@/lib/api/generated/admin";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { Textarea } from "@/components/atoms/textarea";
import { ResourceForm } from "@/components/organisms/resource-form";

export function KitchenCreatePage() {
  const [community, setCommunity] = useState("");
  return (
    <ResourceForm
      create
      cancelHref={"/kitchens"}
      title="New kitchen"
      submit={(data) =>
        adminFoodCreateKitchen({
          name: String(data.get("name")),
          description: String(data.get("description") ?? "") || null,
          community_id: String(data.get("community_id")),
          owner_user_id: String(data.get("owner_user_id")),
          zone_id: String(data.get("zone_id") ?? "") || null,
          address_label: String(data.get("address_label") ?? "") || null,
          pickup_enabled: data.has("pickup_enabled"),
          delivery_enabled: data.has("delivery_enabled"),
          delivery_fee_paise: Math.round(Number(data.get("delivery_fee") ?? 0) * 100),
          upi_id: String(data.get("upi_id") ?? "") || null,
        })
      }
    >
      <Field label="Kitchen name" id="kitchen_name">
        <Input id="kitchen_name" name="name" required maxLength={150} />
      </Field>
      <Field label="Description" id="description">
        <Textarea id="description" name="description" maxLength={1000} />
      </Field>
      <ReferencePicker
        kind="community"
        name="community_id"
        label="Community"
        value={community}
        onChange={setCommunity}
      />
      <ReferencePicker
        key={community + "owner"}
        kind="user"
        name="owner_user_id"
        label="Owner"
        communityId={community}
      />
      <ReferencePicker
        key={community + "zone"}
        kind="zone"
        name="zone_id"
        label="Kitchen zone"
        communityId={community}
        required={false}
      />
      <Field
        label="Kitchen address"
        id="kitchen_address"
        hint="Independent of the owner’s home address. A pickup point is created when an address is provided."
      >
        <Input id="kitchen_address" name="address_label" maxLength={250} />
      </Field>
      <div className="flex gap-6">
        <label className="flex items-center gap-2 text-sm">
          <Input type="checkbox" name="pickup_enabled" defaultChecked />
          Pickup
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Input type="checkbox" name="delivery_enabled" />
          Delivery
        </label>
      </div>
      <Field label="Delivery fee (₹)" id="delivery_fee">
        <Input
          id="delivery_fee"
          name="delivery_fee"
          type="number"
          min="0"
          max="10000"
          step="0.01"
          defaultValue="0"
        />
      </Field>
      <Field label="UPI ID" id="upi_id">
        <Input id="upi_id" name="upi_id" maxLength={150} />
      </Field>
    </ResourceForm>
  );
}
