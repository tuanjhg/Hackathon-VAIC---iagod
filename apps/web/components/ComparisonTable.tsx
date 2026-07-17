"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { LoaderCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatPrice, stockLabel } from "@/lib/utils";
import { useComparisonStore } from "@/stores/comparison-store";
import type { Product } from "@/types";

export function ComparisonTable() {
  const products = useComparisonStore((state) => state.products); const remove = useComparisonStore((state) => state.remove);
  const ids = products.map((product) => product.id);
  const { data, isLoading, error } = useQuery({ queryKey: ["compare", ids], queryFn: () => api.compare(ids), enabled: ids.length >= 2 });
  if (ids.length < 2) return <div className="state-box">Hãy chọn ít nhất 2 sản phẩm từ trang danh sách.<Button asChild><Link href="/products">Chọn sản phẩm</Link></Button></div>;
  if (isLoading) return <div className="state-box"><LoaderCircle className="animate-spin"/>Đang so sánh...</div>;
  if (error || !data) return <div className="state-box text-red-600">Không tải được kết quả so sánh.</div>;
  const rows: [string, (p: Product) => string][] = [["Giá", (p) => formatPrice(p.sale_price)], ["Công suất", (p) => `${p.capacity_btu.toLocaleString("vi-VN")} BTU`], ["Diện tích", (p) => `${p.recommended_area_min}–${p.recommended_area_max} m²`], ["Inverter", (p) => p.inverter ? "Có" : "Không"], ["Độ ồn", (p) => p.noise_db === null ? "Chưa có dữ liệu" : `${p.noise_db} dB`], ["Bảo hành", (p) => `${p.warranty_months} tháng`], ["Tồn kho", (p) => stockLabel(p.stock_status)], ["Khuyến mãi", (p) => p.promotion?.title ?? "Không có"]];
  return <div className="overflow-x-auto rounded-2xl border bg-white"><table className="w-full min-w-[760px] text-left text-sm"><thead><tr className="bg-slate-50"><th className="w-40 p-4">Tiêu chí</th>{data.products.map((p) => <th key={p.id} className="min-w-52 p-4 align-top"><div className="flex justify-between gap-2"><Link href={`/products/${p.slug}`} className="font-bold text-brand-700">{p.name}</Link><button aria-label={`Bỏ ${p.name}`} onClick={() => remove(p.id)}><X className="h-4 w-4"/></button></div><div className="mt-2 flex flex-wrap gap-1">{data.best_price_id === p.id && <Badge>Giá tốt nhất</Badge>}{data.quietest_id === p.id && <Badge>Êm nhất</Badge>}{data.best_overall_id === p.id && <Badge>Phù hợp tổng thể</Badge>}</div></th>)}</tr></thead><tbody>{rows.map(([label, render]) => <tr key={label} className="border-t"><th className="p-4 text-slate-500">{label}</th>{data.products.map((p) => <td key={p.id} className="p-4 font-medium">{render(p)}</td>)}</tr>)}</tbody></table></div>;
}
function Badge({ children }: { children: React.ReactNode }) { return <span className="rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-bold text-emerald-700">{children}</span>; }

