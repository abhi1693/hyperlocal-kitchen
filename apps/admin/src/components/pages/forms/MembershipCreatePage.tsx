"use client";
import { useState } from "react";
import { adminCreateMembership } from "@/lib/api/generated/admin";
import { ReferencePicker } from "@/components/molecules/reference-picker";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { ResourceForm } from "@/components/organisms/resource-form";

export function MembershipCreatePage() {
  const [formCommunity, setFormCommunity] = useState("");
  return (
    <ResourceForm
      create
      cancelHref={"/memberships"}
      title="Add membership"
      submit={(data) =>
        adminCreateMembership({
          user_id: String(data.get("user_id")),
          community_id: String(data.get("community_id")),
          zone_id: String(data.get("zone_id") ?? "") || null,
          address_label: String(data.get("address_label") ?? "") || null,
        })
      }
    >
      <ReferencePicker kind="user" name="user_id" label="User" />
      <ReferencePicker
        kind="community"
        name="community_id"
        label="Community"
        value={formCommunity}
        onChange={setFormCommunity}
      />
      <ReferencePicker
        key={formCommunity}
        kind="zone"
        name="zone_id"
        label="Home zone"
        communityId={formCommunity}
        required={false}
      />
      <Field label="Home address" id="home_address">
        <Input id="home_address" name="address_label" maxLength={250} />
      </Field>
    </ResourceForm>
  );
}
