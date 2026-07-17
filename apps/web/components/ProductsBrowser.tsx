"use client";
import { useState } from "react";
import { ProductFilter } from "@/components/ProductFilter";
import { ProductGrid } from "@/components/ProductGrid";
import type { ProductFilters } from "@/types";

export function ProductsBrowser({ initialSearch }: { initialSearch?: string }) {
  const [filters, setFilters] = useState<ProductFilters>({ search: initialSearch, sort: "featured", page_size: 12 });
  return <div className="grid gap-6 lg:grid-cols-[250px_1fr]"><ProductFilter filters={filters} onChange={setFilters}/><div><div className="mb-5 flex items-center justify-between gap-4"><p className="text-sm text-slate-500">Lọc theo nhu cầu của bạn</p><select aria-label="Sắp xếp" value={filters.sort} onChange={(event) => setFilters({ ...filters, sort: event.target.value })} className="input max-w-52"><option value="featured">Nổi bật</option><option value="price_asc">Giá tăng dần</option><option value="price_desc">Giá giảm dần</option></select></div><ProductGrid filters={filters}/></div></div>;
}

