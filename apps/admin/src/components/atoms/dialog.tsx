"use client";
import { Dialog as Primitive } from "radix-ui";
import { X } from "lucide-react";
import { Button } from "./button";
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Primitive.Root open={open} onOpenChange={onOpenChange}>
      <Primitive.Portal>
        <Primitive.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <Primitive.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border bg-background p-6 shadow-lg">
          <Primitive.Title className="text-lg font-semibold">{title}</Primitive.Title>
          <Primitive.Description
            className={description ? "mt-1 text-sm text-muted-foreground" : "sr-only"}
          >
            {description ?? title}
          </Primitive.Description>
          <div className="mt-5">{children}</div>
          <Primitive.Close asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Close dialog"
              className="absolute right-3 top-3"
            >
              <X />
            </Button>
          </Primitive.Close>
        </Primitive.Content>
      </Primitive.Portal>
    </Primitive.Root>
  );
}
