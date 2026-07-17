import Link from "next/link";
import { CheckCircle2, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatPrice } from "@/lib/utils";
import type { Recommendation } from "@/types";

export function RecommendationCard({ item }: { item: Recommendation }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-primary/20 bg-card shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b border-border bg-primary/5 px-3 py-2">
        <span className="rounded-full bg-primary px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-primary-foreground">
          {item.label}
        </span>
        <span className="flex items-center gap-1 text-sm font-extrabold text-success">
          {item.match_score}%
          <span className="text-[10px] font-semibold text-muted-foreground">phù hợp</span>
        </span>
      </div>

      <div className="p-3">
        <p className="font-heading text-sm font-bold leading-5 text-foreground">{item.product.name}</p>
        <p className="mt-1 font-extrabold text-destructive">{formatPrice(item.product.sale_price)}</p>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{item.reason}</p>

        <div className="mt-2.5 grid gap-1.5">
          {item.strengths.slice(0, 2).map((value) => (
            <span key={value} className="flex items-start gap-1.5 text-xs text-foreground">
              <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0 text-success" />
              {value}
            </span>
          ))}
        </div>

        <p className="mt-2.5 flex items-start gap-1.5 rounded-lg bg-amber-500/10 px-2.5 py-2 text-xs text-amber-700 dark:text-amber-300">
          <TriangleAlert className="mt-px h-3.5 w-3.5 shrink-0" />
          <span>
            <strong className="font-semibold">Đánh đổi:</strong> {item.trade_off}
          </span>
        </p>

        <Button asChild size="sm" className="mt-3 w-full">
          <Link href={`/products/${item.product.slug}`}>Xem chi tiết</Link>
        </Button>
      </div>
    </div>
  );
}
