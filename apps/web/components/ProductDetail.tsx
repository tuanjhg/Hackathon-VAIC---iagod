"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ChevronRight, MessageCircle, ShieldCheck, ShoppingCart, Star } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBox } from "@/components/ui/state";
import { ProductImage } from "@/components/ProductImage";
import { api } from "@/lib/api";
import { formatPrice, stockLabel } from "@/lib/utils";
import { useCartStore } from "@/stores/cart-store";
import { useChatStore } from "@/stores/chat-store";

export function ProductDetail({ slug }: { slug: string }) {
  const { data: product, isLoading, isError } = useQuery({
    queryKey: ["product", slug],
    queryFn: () => api.product(slug),
  });
  const add = useCartStore((s) => s.add);
  const openChat = useChatStore((s) => s.open);

  if (isLoading) return <DetailSkeleton />;
  if (isError || !product)
    return (
      <div className="container py-10">
        <StateBox
          tone="danger"
          title="Không tìm thấy sản phẩm"
          description="Sản phẩm không tồn tại hoặc không tải được. Quay lại catalog để chọn sản phẩm khác."
          action={
            <Button asChild variant="outline">
              <Link href="/products">Về danh sách</Link>
            </Button>
          }
        />
      </div>
    );

  const specs: [string, string][] = [
    ["Công suất", product.capacity_btu > 0 ? `${product.capacity_btu.toLocaleString("vi-VN")} BTU (${product.horsepower} HP)` : "Chưa có dữ liệu"],
    ["Diện tích phù hợp", product.recommended_area_max > 0 ? `${product.recommended_area_min}–${product.recommended_area_max} m²` : "Chưa có dữ liệu"],
    ["Công nghệ", product.inverter ? "Inverter" : "Không Inverter"],
    ["Độ ồn", product.noise_db === null ? "Chưa có dữ liệu" : `${product.noise_db} dB`],
    ["Nhãn năng lượng", product.energy_rating],
    ["Bảo hành", product.warranty_months > 0 ? `${product.warranty_months} tháng` : "Chưa có dữ liệu"],
  ];
  const isUnavailable = !["in_stock", "low_stock"].includes(product.stock_status);

  return (
    <div className="container py-8">
      <nav className="flex items-center gap-1 text-sm text-muted-foreground" aria-label="Breadcrumb">
        <Link href="/" className="hover:text-foreground">Trang chủ</Link>
        <ChevronRight className="h-4 w-4" />
        <Link href="/products" className="hover:text-foreground">Sản phẩm</Link>
        <ChevronRight className="h-4 w-4" />
        <span className="truncate text-foreground">{product.name}</span>
      </nav>

      <div className="mt-6 grid gap-10 lg:grid-cols-2">
        <ProductImage
          src={product.image_url}
          alt={product.name}
          priority
          sizes="(max-width: 1024px) 100vw, 50vw"
          className="rounded-3xl border border-border"
        />

        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold uppercase tracking-wider text-primary">{product.brand}</span>
            {product.inverter && <Badge variant="accent">Inverter</Badge>}
          </div>
          <h1 className="mt-2 font-heading text-3xl font-extrabold leading-tight">{product.name}</h1>
          <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
            <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
            {product.review_count > 0
              ? `${product.rating} · ${product.review_count} đánh giá`
              : "Chưa có đánh giá"}
          </p>

          <div className="mt-6 flex items-baseline gap-3">
            <span className="text-3xl font-extrabold text-destructive">
              {formatPrice(product.sale_price)}
            </span>
            {Number(product.original_price) > Number(product.sale_price) && (
              <span className="text-muted-foreground line-through">
                {formatPrice(product.original_price)}
              </span>
            )}
          </div>

          {product.promotion && (
            <div className="mt-4 rounded-xl border border-destructive/20 bg-destructive/5 p-3">
              <strong className="text-destructive">{product.promotion.title}</strong>
              <p className="text-sm text-muted-foreground">{product.promotion.description}</p>
            </div>
          )}

          <p
            className={`mt-4 flex items-center gap-2 font-semibold ${
              isUnavailable ? "text-muted-foreground" : "text-success"
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${isUnavailable ? "bg-muted-foreground" : "bg-success"}`} />
            {stockLabel(product.stock_status)}
            {product.stock_status !== "unknown" && ` · ${product.stock_quantity} sản phẩm`}
          </p>

          <p className="mt-5 leading-7 text-muted-foreground">{product.short_description}</p>

          <div className="mt-7 flex flex-wrap gap-3">
            <Button
              size="lg"
              disabled={isUnavailable}
              onClick={() => {
                add(product);
                toast.success("Đã thêm vào giỏ hàng");
              }}
            >
              <ShoppingCart />
              Thêm vào giỏ
            </Button>
            <Button variant="outline" size="lg" onClick={openChat}>
              <MessageCircle />
              Hỏi chatbot
            </Button>
          </div>
        </div>
      </div>

      <div className="mt-12 grid gap-6 lg:grid-cols-3">
        <section className="rounded-2xl border border-border bg-card p-6 shadow-card lg:col-span-2">
          <h2 className="font-heading text-xl font-bold">Thông số cơ bản</h2>
          <dl className="mt-5 divide-y divide-border">
            {specs.map(([label, value]) => (
              <div key={label} className="grid grid-cols-2 py-3 text-sm">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="font-semibold text-foreground">{value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <div className="space-y-5">
          <section className="rounded-2xl border border-success/20 bg-success/5 p-6">
            <ShieldCheck className="h-6 w-6 text-success" />
            <h2 className="mt-3 font-heading font-bold">Chính sách bảo hành</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {product.warranty_months > 0
                ? `Bảo hành chính hãng ${product.warranty_months} tháng theo điều kiện của nhà sản xuất.`
                : "Chưa có dữ liệu bảo hành từ nhà sản xuất."}
            </p>
          </section>
          <section className="rounded-2xl border border-border bg-card p-6 shadow-card">
            <h2 className="font-heading font-bold">Đánh giá gần đây</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Chưa có đánh giá thực tế cho sản phẩm này.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="container py-8">
      <Skeleton className="h-4 w-64" />
      <div className="mt-6 grid gap-10 lg:grid-cols-2">
        <Skeleton className="aspect-[4/3] w-full rounded-3xl" />
        <div className="space-y-4">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-9 w-4/5" />
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-8 w-56" />
          <Skeleton className="h-20 w-full" />
          <div className="flex gap-3">
            <Skeleton className="h-12 w-40" />
            <Skeleton className="h-12 w-40" />
          </div>
        </div>
      </div>
    </div>
  );
}
