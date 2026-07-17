"use client";
import { useState } from "react";
import { ProductFilter } from "@/components/ProductFilter";
import { ProductGrid } from "@/components/ProductGrid";
import { Select } from "@/components/ui/select";
import type { ProductFilters } from "@/types";

export function ProductsBrowser({ initialFilters }: { initialFilters?: ProductFilters }) {
  const [filters, setFilters] = useState<ProductFilters>({
    sort: "featured",
    page_size: 12,
    ...initialFilters,
  });

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
      <ProductFilter filters={filters} onChange={setFilters} />
      <div>
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">Lọc theo nhu cầu của bạn</p>
          <div className="w-48">
            <Select
              aria-label="Sắp xếp"
              value={filters.sort}
              onValueChange={(v) => setFilters({ ...filters, sort: v })}
              options={[
                { value: "featured", label: "Nổi bật" },
                { value: "price_asc", label: "Giá tăng dần" },
                { value: "price_desc", label: "Giá giảm dần" },
              ]}
            />
          </div>
        </div>
        <ProductGrid filters={filters} />
      </div>
    </div>
  );
}
