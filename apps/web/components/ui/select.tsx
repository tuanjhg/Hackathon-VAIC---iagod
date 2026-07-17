"use client";
import * as RSelect from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export type SelectOption = { value: string; label: string; disabled?: boolean };

/**
 * Professional Select built on Radix — a fully styled, token-driven dropdown
 * (custom popover + options) rather than the OS-native list. Keyboard- and
 * screen-reader-accessible out of the box.
 *
 * Radix reserves the empty string, so a "" option/value is mapped to an
 * internal sentinel and mapped back on change — callers keep using "".
 */
const EMPTY = " empty";
const toInner = (v?: string) => (v === "" || v == null ? EMPTY : v);
const toOuter = (v: string) => (v === EMPTY ? "" : v);

export function Select({
  value,
  onValueChange,
  options,
  placeholder = "Chọn…",
  className,
  disabled,
  id,
  "aria-label": ariaLabel,
}: {
  value?: string;
  onValueChange?: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}) {
  return (
    <RSelect.Root
      value={toInner(value)}
      onValueChange={(v) => onValueChange?.(toOuter(v))}
      disabled={disabled}
    >
      <RSelect.Trigger
        id={id}
        aria-label={ariaLabel}
        className={cn(
          "group flex h-11 w-full cursor-pointer items-center justify-between gap-2 rounded-xl border border-input bg-card px-3.5 text-sm text-foreground shadow-sm outline-none transition-colors",
          "hover:border-ring/60 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/35",
          "data-[state=open]:border-ring data-[state=open]:ring-2 data-[state=open]:ring-ring/35",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
      >
        <RSelect.Value placeholder={placeholder} />
        <RSelect.Icon asChild>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </RSelect.Icon>
      </RSelect.Trigger>

      <RSelect.Portal>
        <RSelect.Content
          position="popper"
          sideOffset={6}
          className="select-popover z-50 max-h-64 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-lg"
        >
          <RSelect.Viewport className="p-1.5">
            {options.map((opt) => (
              <RSelect.Item
                key={opt.value}
                value={toInner(opt.value)}
                disabled={opt.disabled}
                className={cn(
                  "relative flex cursor-pointer select-none items-center rounded-lg py-2 pl-3 pr-8 text-sm outline-none transition-colors",
                  "data-[highlighted]:bg-primary/10 data-[highlighted]:text-primary",
                  "data-[state=checked]:font-semibold data-[state=checked]:text-primary",
                  "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
                )}
              >
                <RSelect.ItemText>{opt.label}</RSelect.ItemText>
                <RSelect.ItemIndicator className="absolute right-2.5 inline-flex">
                  <Check className="h-4 w-4" />
                </RSelect.ItemIndicator>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}
