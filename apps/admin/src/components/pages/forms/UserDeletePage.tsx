"use client";
import { useAdminGetUser, adminDeleteUser } from "@/lib/api/generated/admin";
import { QueryState } from "@/components/molecules/query-state";
import { ResourceForm } from "@/components/organisms/resource-form";
export function UserDeletePage({ id }: { id: string }) {
  const query = useAdminGetUser(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  return (
    <ResourceForm
      title="Delete user"
      description={query.data.name ?? "Unnamed user"}
      cancelHref="/users"
      submit={() => adminDeleteUser(id)}
    >
      <p className="text-sm">
        Permanently remove this application profile. Users linked to memberships, kitchens, orders,
        devices or history cannot be deleted; deactivate them instead.
      </p>
      <p className="text-sm text-muted-foreground">
        The Zitadel account remains. Signing in again creates a new application profile.
      </p>
    </ResourceForm>
  );
}
