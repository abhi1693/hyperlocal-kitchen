"use client";
import { useState } from "react";
import { useAdminGetCommunity } from "@/lib/api/generated/admin";
import { Button } from "@/components/atoms/button";
import { Dialog } from "@/components/atoms/dialog";
import { ReferencePicker } from "./reference-picker";
export function CommunityFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(value);
  const community = useAdminGetCommunity(value, { query: { enabled: !!value } });
  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          setSelected(value);
          setOpen(true);
        }}
      >
        {value ? (community.data?.name ?? "Selected community") : "All communities"}
      </Button>
      <Dialog title="Filter by community" open={open} onOpenChange={setOpen}>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onChange(selected);
            setOpen(false);
          }}
        >
          <ReferencePicker
            kind="community"
            name="community_filter"
            label="Community"
            required={false}
            value={selected}
            onChange={setSelected}
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
            >
              Clear
            </Button>
            <Button type="submit">Apply</Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
