"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/atoms/button";
import { Dialog } from "@/components/atoms/dialog";
import { FormError } from "./form-error";
export function ActionButton({
  label,
  action,
  description,
  disabled = false,
}: {
  label: string;
  action: () => Promise<unknown>;
  description?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: action,
    onSuccess: async () => {
      await client.invalidateQueries();
      setOpen(false);
      toast.success(`${label} completed`);
    },
  });
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => {
          mutation.reset();
          setOpen(true);
        }}
      >
        {label}
      </Button>
      <Dialog
        title={label}
        description={description ?? "Confirm this action."}
        open={open}
        onOpenChange={(value) => {
          if (!mutation.isPending) setOpen(value);
        }}
      >
        <div className="space-y-4">
          <FormError error={mutation.error} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={mutation.isPending} onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button loading={mutation.isPending} onClick={() => mutation.mutate()}>
              {label}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
