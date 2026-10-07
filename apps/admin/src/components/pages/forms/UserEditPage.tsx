"use client";
import { adminUpdateUser } from "@/lib/api/generated/admin";
import { QueryState } from "@/components/molecules/query-state";
import { Field } from "@/components/molecules/field";
import { Input } from "@/components/atoms/input";
import { ResourceForm } from "@/components/organisms/resource-form";
import { useAdminGetUser } from "@/lib/api/generated/admin";

export function UserEditPage({ id }: { id: string }) {
  const query = useAdminGetUser(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const row = query.data;
  return (
    <ResourceForm
      cancelHref={`/users/${id}`}
      title="Edit user"
      description={row.name ?? "Unnamed user"}
      submit={(data) =>
        adminUpdateUser(row.id, {
          name: String(data.get("name")) || null,
          phone: String(data.get("phone")) || null,
        })
      }
    >
      <Field label="Name" id="user_name">
        <Input id="user_name" name="name" maxLength={120} defaultValue={row.name ?? ""} />
      </Field>
      <Field
        label="Contact phone"
        id="user_phone"
        hint="Use international format, e.g. +919876543210."
      >
        <Input
          id="user_phone"
          name="phone"
          type="tel"
          pattern="\+[1-9][0-9]{7,14}"
          defaultValue={row.phone ?? ""}
        />
      </Field>
    </ResourceForm>
  );
}
