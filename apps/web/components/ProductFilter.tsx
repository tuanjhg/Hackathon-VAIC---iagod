"use client";
import type { ProductFilters } from "@/types";

export function ProductFilter({ filters, onChange }: { filters: ProductFilters; onChange: (filters: ProductFilters) => void }) {
  const update = (key: keyof ProductFilters, value: string | number | boolean | undefined) => onChange({ ...filters, [key]: value, page: 1 });
  return <aside className="h-fit rounded-2xl border bg-white p-5 shadow-card"><h2 className="text-lg font-bold">Bộ lọc</h2><div className="mt-5 grid gap-5">
    <label className="filter-label">Từ khóa<input value={filters.search ?? ""} onChange={(e) => update("search", e.target.value || undefined)} placeholder="Tên hoặc thương hiệu" className="input"/></label>
    <label className="filter-label">Khoảng giá<select value={filters.max_price ?? ""} onChange={(e) => update("max_price", e.target.value ? Number(e.target.value) : undefined)} className="input"><option value="">Tất cả</option><option value="10000000">Dưới 10 triệu</option><option value="15000000">Dưới 15 triệu</option><option value="20000000">Dưới 20 triệu</option></select></label>
    <label className="filter-label">Thương hiệu<select value={filters.brand ?? ""} onChange={(e) => update("brand", e.target.value || undefined)} className="input"><option value="">Tất cả</option>{["Daikin","Panasonic","LG","Samsung","Casper"].map((brand) => <option key={brand}>{brand}</option>)}</select></label>
    <label className="filter-label">Diện tích phòng<select value={filters.room_area ?? ""} onChange={(e) => update("room_area", e.target.value ? Number(e.target.value) : undefined)} className="input"><option value="">Tất cả</option><option value="12">Dưới 15 m²</option><option value="18">15–20 m²</option><option value="25">20–30 m²</option></select></label>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={filters.inverter === true} onChange={(e) => update("inverter", e.target.checked ? true : undefined)}/> Chỉ máy Inverter</label>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={filters.in_stock === true} onChange={(e) => update("in_stock", e.target.checked ? true : undefined)}/> Chỉ sản phẩm còn hàng</label>
  </div></aside>;
}

