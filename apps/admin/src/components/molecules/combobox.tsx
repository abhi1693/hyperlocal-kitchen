"use client";

import { useId, useRef, useState, type AriaAttributes, type ReactNode } from "react";
import { Popover } from "radix-ui";
import { Check, ChevronDown, LoaderCircle, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/atoms/button";

export type ComboboxOption = { value: string; label: string; keywords?: string[] };
export type ComboboxProps = AriaAttributes & {
  id?: string;
  name?: string;
  label: string;
  options: readonly ComboboxOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  selectedOption?: ComboboxOption;
  required?: boolean;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  search?: string;
  onSearchChange?: (value: string) => void;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
  footer?: ReactNode;
};

/** One searchable control for both fixed choices and paginated API references. */
export function Combobox({
  id,
  name,
  label,
  options,
  value,
  defaultValue,
  onValueChange,
  selectedOption,
  required = false,
  disabled = false,
  placeholder = "Select…",
  className,
  search,
  onSearchChange,
  loading = false,
  error,
  onRetry,
  footer,
  ...aria
}: ComboboxProps) {
  const generatedId = useId();
  const triggerId = id ?? generatedId;
  const listId = `${generatedId}-list`;
  const searchId = `${generatedId}-search`;
  const trigger = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [localValue, setLocalValue] = useState(defaultValue ?? options[0]?.value ?? "");
  const [localSearch, setLocalSearch] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const [retained, setRetained] = useState<ComboboxOption>();
  const chosen = value ?? localValue;
  const query = search ?? localSearch;
  const selected =
    options.find((option) => option.value === chosen) ??
    (selectedOption?.value === chosen
      ? selectedOption
      : retained?.value === chosen
        ? retained
        : undefined);
  const normalize = (text: string) =>
    text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  const visible = onSearchChange
    ? options
    : options.filter((option) =>
        normalize([option.label, option.value, ...(option.keywords ?? [])].join(" ")).includes(
          normalize(query.trim()),
        ),
      );
  const activeIndex = visible.findIndex((option) => option.value === active);
  const focusedIndex = activeIndex >= 0 ? activeIndex : visible.length ? 0 : -1;
  const invalid = missing && required && !chosen;

  function updateSearch(next: string) {
    setLocalSearch(next);
    onSearchChange?.(next);
    setActive(null);
  }
  function changeOpen(next: boolean) {
    if (next && (disabled || trigger.current?.matches(":disabled"))) return;
    setOpen(next);
    updateSearch("");
    setActive(chosen);
  }
  function choose(next: string) {
    if (disabled || loading || error || trigger.current?.matches(":disabled")) return;
    setRetained(options.find((option) => option.value === next));
    setLocalValue(next);
    onValueChange?.(next);
    setMissing(false);
    changeOpen(false);
  }
  function highlight(index: number) {
    if (!visible.length) return;
    const next = (index + visible.length) % visible.length;
    setActive(visible[next].value);
    document.getElementById(`${listId}-${next}`)?.scrollIntoView({ block: "nearest" });
  }
  return (
    <div className={cn("relative min-w-0 w-full", className)}>
      {/* A native validation bridge preserves required checks, FormData and fieldset disabling. */}
      {(name || required) && (
        <select
          aria-hidden
          tabIndex={-1}
          name={name}
          required={required}
          disabled={disabled}
          className="pointer-events-none absolute size-px opacity-0"
          value={chosen}
          onChange={(event) => {
            setLocalValue(event.target.value);
            onValueChange?.(event.target.value);
          }}
          onInvalid={(event) => {
            event.preventDefault();
            setMissing(true);
            const first = event.currentTarget.form?.querySelector(
              "input:invalid, select:invalid, textarea:invalid",
            );
            if (!first || first === event.currentTarget) {
              trigger.current?.focus();
              changeOpen(true);
            }
          }}
        >
          <option value="" />
          {chosen && <option value={chosen}>{selected?.label ?? chosen}</option>}
        </select>
      )}
      <Popover.Root open={open && !disabled} onOpenChange={changeOpen}>
        <Popover.Trigger asChild>
          <Button
            ref={trigger}
            id={triggerId}
            variant="outline"
            role="combobox"
            aria-label={label}
            aria-expanded={open && !disabled}
            aria-controls={open ? listId : undefined}
            aria-haspopup="listbox"
            aria-required={required}
            {...aria}
            aria-invalid={invalid || aria["aria-invalid"]}
            aria-describedby={
              [aria["aria-describedby"], invalid ? `${triggerId}-required` : undefined]
                .filter(Boolean)
                .join(" ") || undefined
            }
            disabled={disabled}
            className="w-full justify-between gap-2 font-normal"
            onKeyDown={(event) => {
              if (["ArrowDown", "ArrowUp"].includes(event.key)) {
                event.preventDefault();
                changeOpen(true);
              }
            }}
          >
            <span
              className={cn(
                "min-w-0 flex-1 truncate text-left",
                !selected && "text-muted-foreground",
              )}
            >
              {selected?.label ?? placeholder}
            </span>
            <ChevronDown className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          </Button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            aria-label={`${label} options`}
            align="start"
            sideOffset={6}
            collisionPadding={12}
            className="z-50 flex w-[var(--radix-popover-trigger-width)] min-w-[min(16rem,calc(100vw-1.5rem))] max-w-[calc(100vw-1.5rem)] max-h-[min(24rem,var(--radix-popover-content-available-height))] flex-col overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-lg"
            onOpenAutoFocus={(event) => {
              event.preventDefault();
              input.current?.focus();
            }}
          >
            <div className="flex shrink-0 items-center gap-2 border-b px-3">
              <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <input
                ref={input}
                id={searchId}
                role="combobox"
                autoComplete="off"
                aria-label={`Search ${label.toLowerCase()}`}
                aria-expanded
                aria-controls={listId}
                aria-autocomplete="list"
                aria-activedescendant={
                  !loading && !error && focusedIndex >= 0 ? `${listId}-${focusedIndex}` : undefined
                }
                className="h-10 min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted-foreground md:text-sm"
                placeholder={`Search ${label.toLowerCase()}…`}
                maxLength={200}
                value={query}
                onChange={(event) => updateSearch(event.target.value)}
                onKeyDown={(event) => {
                  if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
                    if ((event.key === "Home" || event.key === "End") && !event.ctrlKey) return;
                    event.preventDefault();
                    if (loading || error) return;
                    highlight(
                      event.key === "Home"
                        ? 0
                        : event.key === "End"
                          ? visible.length - 1
                          : focusedIndex + (event.key === "ArrowDown" ? 1 : -1),
                    );
                  } else if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                    event.preventDefault();
                    if (focusedIndex >= 0) choose(visible[focusedIndex].value);
                  }
                }}
              />
            </div>
            <div
              id={listId}
              role="listbox"
              aria-label={`${label} choices`}
              aria-busy={loading}
              className="min-h-0 flex-1 overflow-y-auto p-1"
            >
              {loading ? (
                <div
                  role="status"
                  className="flex items-center justify-center gap-2 p-6 text-sm text-muted-foreground"
                >
                  <LoaderCircle
                    aria-hidden
                    className="size-4 animate-spin motion-reduce:animate-none"
                  />
                  Loading options…
                </div>
              ) : error ? (
                <div role="alert" className="space-y-3 p-4 text-sm">
                  <p>{error}</p>
                  {onRetry && (
                    <Button size="sm" variant="outline" onClick={onRetry}>
                      Retry
                    </Button>
                  )}
                </div>
              ) : (
                <>
                  {visible.map((option, index) => (
                    <div
                      id={`${listId}-${index}`}
                      key={option.value}
                      role="option"
                      aria-selected={chosen === option.value}
                      data-highlighted={focusedIndex === index || undefined}
                      className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground"
                      onPointerMove={() => setActive(option.value)}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => choose(option.value)}
                    >
                      <span className="min-w-0 flex-1 break-words">{option.label}</span>
                      <Check
                        aria-hidden
                        className={cn("size-4 shrink-0", chosen !== option.value && "invisible")}
                      />
                    </div>
                  ))}
                  {!visible.length && (
                    <p role="status" className="p-5 text-center text-sm text-muted-foreground">
                      No results found.
                    </p>
                  )}
                </>
              )}
            </div>
            {!loading && !error && footer && <div className="shrink-0 border-t p-2">{footer}</div>}
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
      {invalid && (
        <p id={`${triggerId}-required`} role="alert" className="mt-2 text-xs text-destructive">
          Select {label.toLowerCase()}.
        </p>
      )}
    </div>
  );
}
