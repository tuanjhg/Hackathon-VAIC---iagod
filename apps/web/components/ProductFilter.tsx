"use client";
import { SlidersHorizontal, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type { ProductFilters } from "@/types";

const BRANDS = ["Daikin", "Panasonic", "LG", "Samsung", "Casper"];

export function ProductFilter({
  filters,
  onChange,
}: {
  filters: ProductFilters;
  onChange: (filters: ProductFilters) => void;
}) {
  const update = (key: keyof ProductFilters, value: string | number | boolean | undefined) =>
    onChange({ ...filters, [key]: value, page: 1 });

  const activeCount = [
    filters.search,
    filters.brand,
    filters.max_price,
    filters.room_area,
    filters.inverter,
    filters.in_stock,
  ].filter(Boolean).length;

  return (
    <aside className="h-fit rounded-2xl border border-border bg-card p-5 shadow-card lg:sticky lg:top-20">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-heading text-lg font-bold">
          <SlidersHorizontal className="h-4 w-4 text-primary" />
          Bộ lọc
        </h2>
        {activeCount > 0 && (
          <button
            onClick={() => onChange({ sort: filters.sort, page_size: filters.page_size, page: 1 })}
            className="flex items-center gap-1 text-xs font-semibold text-muted-foreground hover:text-destructive"
          >
            <X className="h-3.5 w-3.5" />
            Xóa lọc ({activeCount})
          </button>
        )}
      </div>

      <div className="mt-5 grid gap-5">
        <Field label="Từ khóa">
          <Input
            value={filters.search ?? ""}
            onChange={(e) => update("search", e.target.value || undefined)}
            placeholder="Tên hoặc thương hiệu"
          />
        </Field>

        <Field label="Khoảng giá">
          <Select
            aria-label="Khoảng giá"
            value={filters.max_price != null ? String(filters.max_price) : ""}
            onValueChange={(v) => update("max_price", v ? Number(v) : undefined)}
            options={[
              { value: "", label: "Tất cả" },
              { value: "10000000", label: "Dưới 10 triệu" },
              { value: "15000000", label: "Dưới 15 triệu" },
              { value: "20000000", label: "Dưới 20 triệu" },
            ]}
          />
        </Field>

        <Field label="Thương hiệu">
          <Select
            aria-label="Thương hiệu"
            value={filters.brand ?? ""}
            onValueChange={(v) => update("brand", v || undefined)}
            options={[
              { value: "", label: "Tất cả" },
              ...BRANDS.map((brand) => ({ value: brand, label: brand })),
            ]}
          />
        </Field>

        <Field label="Diện tích phòng">
          <Select
            aria-label="Diện tích phòng"
            value={filters.room_area != null ? String(filters.room_area) : ""}
            onValueChange={(v) => update("room_area", v ? Number(v) : undefined)}
            options={[
              { value: "", label: "Tất cả" },
              { value: "12", label: "Dưới 15 m²" },
              { value: "18", label: "15–20 m²" },
              { value: "25", label: "20–30 m²" },
            ]}
          />
        </Field>

        <div className="grid gap-3 border-t border-border pt-4">
          <Toggle
            checked={filters.inverter === true}
            onChange={(v) => update("inverter", v || undefined)}
            label="Chỉ máy Inverter"
          />
          <Toggle
            checked={filters.in_stock === true}
            onChange={(v) => update("in_stock", v || undefined)}
            label="Chỉ sản phẩm còn hàng"
          />
        </div>
      </div>
    </aside>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-2 text-sm font-semibold text-foreground">
      {label}
      {children}
    </label>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 text-sm text-foreground">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-input text-primary accent-[rgb(var(--primary))] focus-visible:ring-2 focus-visible:ring-ring/35"
      />
      {label}
    </label>
  );
}
