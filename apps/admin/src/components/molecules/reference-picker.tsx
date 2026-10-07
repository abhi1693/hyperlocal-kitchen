"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  adminListCommunities,
  adminListUsers,
  adminListMemberships,
  adminListCommunityZones,
} from "@/lib/api/generated/admin";
import { Field } from "./field";
import { Input } from "@/components/atoms/input";
import { Select } from "@/components/atoms/select";
import { Button } from "@/components/atoms/button";
export function ReferencePicker({
  kind,
  name,
  label,
  communityId,
  required = true,
  value,
  onChange,
}: {
  kind: "community" | "user" | "zone";
  name: string;
  label: string;
  communityId?: string;
  required?: boolean;
  value?: string;
  onChange?: (value: string) => void;
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
    queryKey: ["reference", kind, communityId, q, offset],
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
  const options =
    selected && !items.some((row) => row.id === selected.id) ? [selected, ...items] : items;
  return (
    <Field label={label} id={name}>
      <Input
        aria-label={`Search ${label.toLowerCase()}`}
        placeholder={`Search ${label.toLowerCase()}…`}
        value={search}
        maxLength={200}
        onChange={(event) => {
          setSearch(event.target.value);
          setOffset(0);
        }}
        disabled={kind === "zone" && !communityId}
      />
      <Select
        id={name}
        name={name}
        required={required}
        value={value ?? selected?.id ?? ""}
        disabled={(kind === "zone" && !communityId) || query.isPending || !!query.error}
        onChange={(event) => {
          const option = options.find((row) => row.id === event.target.value);
          setSelected(option ?? null);
          onChange?.(event.target.value);
        }}
      >
        <option value="">
          {query.isPending && query.fetchStatus === "fetching"
            ? "Loading…"
            : required
              ? "Select…"
              : "None"}
        </option>
        {options.map((row) => (
          <option key={row.id} value={row.id}>
            {row.label}
          </option>
        ))}
      </Select>
      {query.error && (
        <div role="alert" className="text-sm">
          <p>{query.error.message}</p>
          <Button size="sm" variant="outline" onClick={() => query.refetch()}>
            Retry
          </Button>
        </div>
      )}
      {(query.data?.total ?? 0) > 30 && (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 30))}
          >
            Previous
          </Button>
          <span className="text-xs text-muted-foreground">
            {offset + 1}–{Math.min(offset + 30, query.data!.total)}
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
      )}
    </Field>
  );
}
