"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/atoms/button";
import { Dialog } from "@/components/atoms/dialog";
import { FormError } from "@/components/molecules/form-error";
export function FormDialog({
  title,
  label,
  description,
  children,
  submit,
}: {
  title: string;
  label?: string;
  description?: string;
  children: React.ReactNode;
  submit: (data: FormData) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: submit,
    onSuccess: async () => {
      await client.invalidateQueries();
      setOpen(false);
      toast.success("Saved");
    },
  });
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          mutation.reset();
          setOpen(true);
        }}
      >
        {label ?? title}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!mutation.isPending) setOpen(value);
        }}
        title={title}
        description={description}
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate(new FormData(event.currentTarget));
          }}
        >
          <fieldset disabled={mutation.isPending} className="space-y-4">
            {children}
          </fieldset>
          <FormError error={mutation.error} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={mutation.isPending} onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              Save
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
