"use client";
import Link from "next/link";
import { GitCompareArrows, ShoppingCart, Star } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ProductImage } from "@/components/ProductImage";
import { formatPrice, stockLabel } from "@/lib/utils";
import { useCartStore } from "@/stores/cart-store";
import { useComparisonStore } from "@/stores/comparison-store";
import type { Product } from "@/types";

export function ProductCard({ product }: { product: Product }) {
  const addCart = useCartStore((s) => s.add);
  const addCompare = useComparisonStore((s) => s.add);
  const isOut = product.stock_status === "out_of_stock";
  const discount = Math.round(
    (1 - Number(product.sale_price) / Number(product.original_price)) * 100,
  );

  const handleCompare = () => {
    const before = useComparisonStore.getState().products;
    if (addCompare(product)) toast.success("Đã thêm vào so sánh");
    else
      toast.error(
        before.length >= 3 ? "Chỉ so sánh tối đa 3 sản phẩm" : "Sản phẩm đã có trong so sánh",
      );
  };

  return (
    <article className="group flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-card transition-all duration-300 hover:-translate-y-1 hover:shadow-lg">
      <Link href={`/products/${product.slug}`} className="relative block">
        <ProductImage src={product.image_url} alt={product.name} />
        <div className="absolute left-3 top-3 flex flex-col gap-1.5">
          {product.promotion && <Badge variant="danger">{product.promotion.title}</Badge>}
          {discount > 0 && <Badge variant="solid">-{discount}%</Badge>}
        </div>
        {product.inverter && (
          <Badge variant="accent" className="absolute right-3 top-3 backdrop-blur">
            Inverter
          </Badge>
        )}
      </Link>

      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-center justify-between text-xs">
          <span className="font-bold uppercase tracking-wide text-primary">{product.brand}</span>
          <span className="flex items-center gap-1 text-muted-foreground">
            <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
            {product.rating} ({product.review_count})
          </span>
        </div>

        <Link
          href={`/products/${product.slug}`}
          className="mt-2 line-clamp-2 min-h-[3rem] font-heading font-semibold leading-6 text-foreground transition-colors hover:text-primary"
        >
          {product.name}
        </Link>

        <div className="mt-3 flex items-baseline gap-2">
          <span className="text-lg font-extrabold text-destructive">{formatPrice(product.sale_price)}</span>
          {discount > 0 && (
            <span className="text-xs text-muted-foreground line-through">
              {formatPrice(product.original_price)}
            </span>
          )}
        </div>

        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <div>{product.capacity_btu.toLocaleString("vi-VN")} BTU</div>
          <div>
            {product.recommended_area_min}–{product.recommended_area_max} m²
          </div>
          <div>{product.energy_rating}</div>
          <div>{product.noise_db === null ? "Chưa có dữ liệu" : `${product.noise_db} dB`}</div>
        </dl>

        <p
          className={`mt-3 flex items-center gap-1.5 text-xs font-semibold ${
            isOut ? "text-destructive" : "text-success"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${isOut ? "bg-destructive" : "bg-success"}`} />
          {stockLabel(product.stock_status)}
        </p>

        <div className="mt-auto grid grid-cols-2 gap-2 pt-4">
          <Button variant="outline" size="sm" asChild>
            <Link href={`/products/${product.slug}`}>Chi tiết</Link>
          </Button>
          <Button
            size="sm"
            disabled={isOut}
            onClick={() => {
              addCart(product);
              toast.success("Đã thêm vào giỏ hàng");
            }}
          >
            <ShoppingCart className="h-4 w-4" />
            Thêm giỏ
          </Button>
          <Button className="col-span-2" variant="subtle" size="sm" onClick={handleCompare}>
            <GitCompareArrows className="h-4 w-4" />
            Thêm vào so sánh
          </Button>
        </div>
      </div>
    </article>
  );
}

export function ProductCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-card">
      <div className="aspect-[4/3] w-full animate-pulse bg-muted" />
      <div className="space-y-3 p-4">
        <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
        <div className="h-5 w-4/5 animate-pulse rounded bg-muted" />
        <div className="h-6 w-1/2 animate-pulse rounded bg-muted" />
        <div className="h-8 w-full animate-pulse rounded bg-muted" />
      </div>
    </div>
  );
}
