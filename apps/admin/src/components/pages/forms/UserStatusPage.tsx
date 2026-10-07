"use client";
import { useAdminGetUser, adminActivateUser, adminDeactivateUser } from "@/lib/api/generated/admin";
import { QueryState } from "@/components/molecules/query-state";
import { ResourceForm } from "@/components/organisms/resource-form";
import { StatusBadge } from "@/components/molecules/status-badge";

export function UserStatusPage({ id, active }: { id: string; active: boolean }) {
  const query = useAdminGetUser(id);
  if (!query.data)
    return (
      <QueryState pending={query.isPending} error={query.error} retry={() => query.refetch()} />
    );
  const user = query.data;
  return (
    <ResourceForm
      cancelHref={`/users/${id}`}
      title={active ? "Activate user" : "Deactivate user"}
      description={user.name ?? "Unnamed user"}
      submit={() => (active ? adminActivateUser(id) : adminDeactivateUser(id))}
    >
      <div className="space-y-4 text-sm">
        <p>
          Current status: <StatusBadge value={user.is_active ? "active" : "inactive"} />
        </p>
        {active ? (
          <p>
            Reactivate this account. Suspended community memberships must be restored separately.
          </p>
        ) : (
          <>
            <p>
              This disables the account, suspends its community memberships and disables its
              registered notification devices. A kitchen that loses its last active owner will be
              suspended.
            </p>
            <p>Orders and account history are retained. You can reactivate the account later.</p>
          </>
        )}
      </div>
    </ResourceForm>
  );
}
