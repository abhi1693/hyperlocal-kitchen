"use client";
import { useAdminGetCommunity } from "@/lib/api/generated/admin";
import { ReferencePicker } from "./reference-picker";
export function CommunityFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const community = useAdminGetCommunity(value, { query: { enabled: !!value } });
  return (
    <ReferencePicker
      kind="community"
      name="community_filter"
      label="Community filter"
      inline
      required={false}
      emptyLabel="All communities"
      value={value}
      selectedLabel={community.data?.name}
      onChange={onChange}
    />
  );
}
