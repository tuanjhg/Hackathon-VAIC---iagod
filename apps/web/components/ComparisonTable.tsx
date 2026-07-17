"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { GitCompareArrows, LoaderCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StateBox } from "@/components/ui/state";
import { api } from "@/lib/api";
import { formatPrice, stockLabel } from "@/lib/utils";
import { useComparisonStore } from "@/stores/comparison-store";
import type { Product } from "@/types";

export function ComparisonTable() {
  const products = useComparisonStore((s) => s.products);
  const remove = useComparisonStore((s) => s.remove);
  const ids = products.map((p) => p.id);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["compare", ids],
    queryFn: () => api.compare(ids),
    enabled: ids.length >= 2,
  });

  if (ids.length < 2)
    return (
      <StateBox
        icon={<GitCompareArrows className="h-6 w-6" />}
        title="Chưa đủ sản phẩm để so sánh"
        description="Hãy chọn ít nhất 2 sản phẩm (tối đa 3) từ trang danh sách."
        action={
          <Button asChild>
            <Link href="/products">Chọn sản phẩm</Link>
          </Button>
        }
      />
    );
  if (isLoading)
    return (
      <StateBox
        icon={<LoaderCircle className="h-6 w-6 animate-spin" />}
        title="Đang so sánh…"
      />
    );
  if (isError || !data)
    return <StateBox tone="danger" title="Không tải được kết quả so sánh" />;

  const rows: [string, (p: Product) => string][] = [
    ["Giá", (p) => formatPrice(p.sale_price)],
    ["Công suất", (p) => `${p.capacity_btu.toLocaleString("vi-VN")} BTU`],
    ["Diện tích", (p) => `${p.recommended_area_min}–${p.recommended_area_max} m²`],
    ["Inverter", (p) => (p.inverter ? "Có" : "Không")],
    ["Độ ồn", (p) => (p.noise_db === null ? "Chưa có dữ liệu" : `${p.noise_db} dB`)],
    ["Bảo hành", (p) => `${p.warranty_months} tháng`],
    ["Tồn kho", (p) => stockLabel(p.stock_status)],
    ["Khuyến mãi", (p) => p.promotion?.title ?? "Không có"],
  ];

  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-card shadow-card">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead>
          <tr className="bg-muted/50">
            <th className="w-40 p-4 font-heading text-muted-foreground">Tiêu chí</th>
            {data.products.map((p) => (
              <th key={p.id} className="min-w-52 p-4 align-top">
                <div className="flex justify-between gap-2">
                  <Link href={`/products/${p.slug}`} className="font-heading font-bold text-primary hover:underline">
                    {p.name}
                  </Link>
                  <button
                    aria-label={`Bỏ ${p.name}`}
                    onClick={() => remove(p.id)}
                    className="text-muted-foreground transition-colors hover:text-destructive"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {data.best_price_id === p.id && <Badge variant="success">Giá tốt nhất</Badge>}
                  {data.quietest_id === p.id && <Badge variant="accent">Êm nhất</Badge>}
                  {data.best_overall_id === p.id && <Badge variant="default">Phù hợp tổng thể</Badge>}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, render]) => (
            <tr key={label} className="border-t border-border">
              <th className="p-4 font-medium text-muted-foreground">{label}</th>
              {data.products.map((p) => (
                <td key={p.id} className="p-4 font-medium text-foreground">
                  {render(p)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
