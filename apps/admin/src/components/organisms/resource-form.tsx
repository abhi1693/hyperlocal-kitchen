"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/atoms/button";
import { PageHeading } from "@/components/molecules/page-heading";
import { FormError } from "@/components/molecules/form-error";

export function ResourceForm({
  title,
  description,
  children,
  submit,
  cancelHref,
  create = false,
  submitDisabled = false,
  onCreateAnother,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  submit: (data: FormData) => Promise<unknown>;
  cancelHref: string;
  create?: boolean;
  submitDisabled?: boolean;
  onCreateAnother?: () => void;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const form = useRef<HTMLFormElement>(null);
  const saving = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [version, setVersion] = useState(0);
  const creating = create;
  const parentLabel = cancelHref.startsWith("/communities/")
    ? "Community"
    : cancelHref.startsWith("/kitchens/")
      ? "Kitchen"
      : cancelHref.startsWith("/users/")
        ? "User"
        : cancelHref.startsWith("/orders/")
          ? "Order"
          : cancelHref.slice(1).replace(/^./, (c) => c.toUpperCase());
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving.current) return;
    const data = new FormData(event.currentTarget);
    const another =
      (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "create-another";
    saving.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await submit(data);
      await client.invalidateQueries();
      toast.success(creating ? "Created" : "Saved");
      if (another) {
        if (onCreateAnother) onCreateAnother();
        else setVersion((v) => v + 1);
        requestAnimationFrame(() =>
          form.current
            ?.querySelector<HTMLElement>(
              'input:not([type="hidden"]):not([aria-hidden]), button[role="combobox"], textarea',
            )
            ?.focus(),
        );
      } else {
        const id =
          result && typeof result === "object" && "id" in result ? String(result.id) : undefined;
        const destination =
          creating && id && ["/communities", "/kitchens", "/orders"].includes(cancelHref)
            ? `${cancelHref}/${id}`
            : cancelHref;
        router.push(destination);
        router.refresh();
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure : new Error("Could not save"));
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="max-w-4xl space-y-6">
      <nav
        aria-label="Breadcrumb"
        className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground"
      >
        <Link href={cancelHref} className="hover:underline">
          {parentLabel}
        </Link>
        <span aria-hidden>/</span>
        <span aria-current="page">{title}</span>
      </nav>
      <PageHeading title={title} description={description} />
      <form
        ref={form}
        onSubmit={save}
        aria-busy={busy}
        className="space-y-6 rounded-lg border bg-card p-4 sm:p-6"
      >
        <FormError error={error} />
        <fieldset key={version} disabled={busy} className="space-y-5">
          {children}
        </fieldset>
        <div className="flex flex-wrap justify-end gap-2 border-t pt-5">
          <Button asChild variant="outline" disabled={busy}>
            <Link href={cancelHref}>Cancel</Link>
          </Button>
          <Button type="submit" disabled={submitDisabled} loading={busy} loadingText="Saving…">
            {title.startsWith("Edit") ? "Save changes" : title.replace(/^New /, "Create ")}
          </Button>
          {creating && (
            <Button
              type="submit"
              value="create-another"
              variant="outline"
              disabled={busy || submitDisabled}
            >
              Create and add another
            </Button>
          )}
        </div>
      </form>
    </section>
  );
}
