"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  adminListCommunities,
  adminFoodKitchens,
  adminListUsers,
  adminListMemberships,
  adminListCommunityZones,
} from "@/lib/api/generated/admin";
import { Field } from "./field";
import { Combobox } from "./combobox";
import { Button } from "@/components/atoms/button";
export function ReferencePicker({
  kind,
  name,
  label,
  communityId,
  required = true,
  value,
  onChange,
  inline = false,
  emptyLabel = "None",
  selectedLabel,
  approvedKitchensOnly = true,
}: {
  kind: "community" | "user" | "zone" | "kitchen";
  name: string;
  label: string;
  communityId?: string;
  required?: boolean;
  value?: string;
  onChange?: (value: string) => void;
  inline?: boolean;
  emptyLabel?: string;
  selectedLabel?: string;
  approvedKitchensOnly?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<{
    id: string;
    label: string;
  } | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setQ(search), 250);
    return () => clearTimeout(timer);
  }, [search]);
  useEffect(() => {
    setSelected(null);
    setOffset(0);
  }, [communityId]);
  const query = useQuery({
    queryKey: ["reference", kind, communityId, q, offset, approvedKitchensOnly],
    enabled: kind !== "zone" || !!communityId,
    queryFn: async ({ signal }) => {
      const params = { q, limit: 30, offset };
      if (kind === "community") {
        const page = await adminListCommunities(params, { signal });
        return {
          total: page.total,
          items: page.items.map((row) => ({
            id: row.id,
            label: `${row.name} · ${row.city}`,
          })),
        };
      }
      if (kind === "kitchen") {
        const page = await adminFoodKitchens(
          {
            ...params,
            status: approvedKitchensOnly ? "approved" : undefined,
            community_id: communityId || undefined,
          },
          { signal },
        );
        return {
          total: page.total,
          items: page.items.map((row) => ({
            id: row.id,
            label: `${row.name} · ${row.community_name}`,
          })),
        };
      }
      if (kind === "zone") {
        const page = await adminListCommunityZones(communityId!, params, {
          signal,
        });
        return {
          total: page.total,
          items: page.items.map((row) => ({ id: row.id, label: row.name })),
        };
      }
      if (communityId) {
        const page = await adminListMemberships(
          { ...params, community_id: communityId, status: "active" },
          { signal },
        );
        return {
          total: page.total,
          items: page.items.map((row) => ({
            id: row.user_id,
            label: row.user_name ?? row.phone ?? "Unnamed resident",
          })),
        };
      }
      const page = await adminListUsers({ ...params, is_active: true }, { signal });
      return {
        total: page.total,
        items: page.items.map((row) => ({
          id: row.id,
          label: row.name ?? row.phone ?? "Unnamed user",
        })),
      };
    },
  });
  const items = query.data?.items ?? [];
  const chosen = value ?? selected?.id ?? "";
  const control = (
    <Combobox
      id={name}
      name={name}
      label={label}
      required={required}
      value={chosen}
      placeholder={kind === "zone" && !communityId ? "Select a community first" : "Select…"}
      className={inline ? "w-auto min-w-44" : undefined}
      options={[
        ...(!required ? [{ value: "", label: emptyLabel }] : []),
        ...items.map((row) => ({ value: row.id, label: row.label })),
      ]}
      selectedOption={
        chosen && (selected?.id === chosen || selectedLabel)
          ? {
              value: chosen,
              label: selected?.id === chosen ? selected.label : selectedLabel!,
            }
          : undefined
      }
      disabled={kind === "zone" && !communityId}
      search={search}
      onSearchChange={(next) => {
        setSearch(next);
        setOffset(0);
      }}
      loading={query.isFetching || search !== q}
      error={query.error?.message}
      onRetry={() => query.refetch()}
      onValueChange={(next) => {
        const option = items.find((row) => row.id === next);
        setSelected(option ?? null);
        onChange?.(next);
      }}
      footer={
        (query.data?.total ?? 0) > 30 && (
          <div className="flex items-center justify-between gap-2">
            <Button
              size="sm"
              variant="ghost"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 30))}
            >
              Previous
            </Button>
            <span className="text-xs text-muted-foreground">
              {offset + 1}–{Math.min(offset + 30, query.data!.total)} of {query.data!.total}
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={offset + 30 >= query.data!.total}
              onClick={() => setOffset(offset + 30)}
            >
              Next
            </Button>
          </div>
        )
      }
    />
  );
  return inline ? (
    control
  ) : (
    <Field label={label} id={name}>
      {control}
    </Field>
  );
}
