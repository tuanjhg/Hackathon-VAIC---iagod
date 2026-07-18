import Link from "next/link";
import { CheckCircle2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProductImage } from "@/components/ProductImage";
import { formatPrice } from "@/lib/utils";
import type { AdvisorCard as AdvisorCardType } from "@/types";

export function AdvisorCard({ item }: { item: AdvisorCardType }) {
  const productPath = item.product_slug || item.sku;

  return (
    <div className="overflow-hidden rounded-2xl border border-brand-500/20 bg-card shadow-md transition-all hover:border-brand-500/40">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-brand-500/5 px-3 py-2">
        <span className="rounded-full bg-brand-600 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-white">
          {item.label}
        </span>
        <span className="flex items-center gap-1 text-sm font-extrabold text-brand-600">
          {item.match_score}%
          <span className="text-[10px] font-semibold text-muted-foreground">điểm tương đối</span>
        </span>
      </div>

      <div className="p-3">
        <div className="flex gap-3">
          <Link
            href={`/products/${productPath}`}
            className="group relative h-16 w-16 shrink-0 overflow-hidden rounded-xl border border-border"
          >
            <ProductImage
              src={item.image_url || ""}
              alt={item.name}
              sizes="64px"
              className="aspect-square h-full"
            />
          </Link>
          <div className="min-w-0">
            <p className="line-clamp-2 font-heading text-sm font-bold leading-5 text-foreground">
              {item.name}
            </p>
            {item.price !== null && (
              <p className="mt-1 font-extrabold text-destructive">{formatPrice(item.price)}</p>
            )}
            {item.price === null && (
              <p className="mt-1 text-xs font-semibold text-muted-foreground">
                Chưa có dữ liệu giá trực tuyến
              </p>
            )}
          </div>
        </div>
        
        {item.reason && (
          <p className="mt-2.5 text-xs leading-5 text-muted-foreground">{item.reason}</p>
        )}

        {item.strengths && item.strengths.length > 0 && (
          <div className="mt-2.5 grid gap-1.5">
            {item.strengths.slice(0, 3).map((value) => (
              <span key={value} className="flex items-start gap-1.5 text-xs text-foreground">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                <span>{value}</span>
              </span>
            ))}
          </div>
        )}

        {item.trade_off && (
          <div className="mt-2.5 flex items-start gap-1.5 rounded-lg bg-amber-500/10 px-2.5 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              <strong className="font-semibold">Đánh đổi:</strong> {item.trade_off}
            </span>
          </div>
        )}

        {item.missing_fields && item.missing_fields.length > 0 && (
          <div className="mt-2 text-[10px] text-muted-foreground italic">
            * Chưa có dữ liệu: {item.missing_fields.join(", ")}. Hệ thống không tự ước lượng.
          </div>
        )}

        <Button asChild size="sm" className="mt-3 w-full bg-brand-600 hover:bg-brand-700 text-white">
          <Link href={`/products/${productPath}`}>Xem chi tiết</Link>
        </Button>
      </div>
    </div>
  );
}
