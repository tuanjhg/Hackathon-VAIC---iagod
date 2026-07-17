"use client";
import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import Link from "next/link";
import { ChevronLeft, ChevronRight, Star } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ProductImage } from "@/components/ProductImage";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { slideRail } from "@/lib/scroll";
import { formatPrice } from "@/lib/utils";
import type { Product, ProductFilters } from "@/types";

type PromoBanner = {
  title: string;
  subtitle: string;
  cta: string;
  href: string;
  /** Tailwind gradient stops for the placeholder / tint, e.g. "from-brand-800 to-accent". */
  tone: string;
  /** Optional real image dropped under /public. */
  src?: string;
};

/**
 * "Promo station" block — a themed banner on the left and a horizontal product
 * rail on the right. Deliberately different from the plain ProductGrid so two
 * adjacent product sections don't read as the same thing.
 */
export function PromoRail({
  icon,
  title,
  banner,
  filters,
  viewAllHref,
  limit = 10,
}: {
  icon?: ReactNode;
  title: string;
  banner: PromoBanner;
  filters: ProductFilters;
  viewAllHref: string;
  limit?: number;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["products", { ...filters, page_size: limit, rail: title }],
    queryFn: () => api.products({ ...filters, page_size: limit }),
  });
  const items = data?.items ?? [];

  const trackRef = useRef<HTMLDivElement>(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);

  const updateEdges = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    setAtStart(el.scrollLeft <= 4);
    setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 4);
  }, []);
  useEffect(() => updateEdges(), [items.length, updateEdges]);

  const slide = (dir: 1 | -1) => {
    const el = trackRef.current;
    if (el) slideRail(el, dir);
  };

  return (
    <section className="container pt-12">
      <div className="overflow-hidden rounded-3xl border border-border bg-card shadow-card">
        {/* header bar */}
        <div className="flex items-center justify-between gap-3 bg-gradient-to-r from-brand-800 via-brand-700 to-accent px-4 py-3.5 sm:px-6">
          <h2 className="flex items-center gap-2.5 font-heading text-lg font-extrabold tracking-tight text-white sm:text-xl">
            {icon}
            {title}
          </h2>
          <Link
            href={viewAllHref}
            className="shrink-0 rounded-full bg-white/15 px-3.5 py-1.5 text-xs font-bold text-white ring-1 ring-white/25 transition-colors hover:bg-white/25"
          >
            Xem tất cả →
          </Link>
        </div>

        {/* body: promo banner + product rail */}
        <div className="flex flex-col gap-4 p-4 lg:flex-row">
          <PromoSide banner={banner} />

          <div className="group relative min-w-0 flex-1">
            <RailArrow side="left" hidden={atStart} onClick={() => slide(-1)} />
            <RailArrow side="right" hidden={atEnd && !isLoading} onClick={() => slide(1)} />

            <div
              ref={trackRef}
              onScroll={updateEdges}
              className="flex gap-3 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            >
              {isLoading
                ? Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="w-[188px] shrink-0 rounded-xl border border-border p-3">
                      <Skeleton className="aspect-square w-full rounded-lg" />
                      <Skeleton className="mt-3 h-4 w-full" />
                      <Skeleton className="mt-1.5 h-4 w-2/3" />
                      <Skeleton className="mt-3 h-5 w-1/2" />
                    </div>
                  ))
                : items.map((p) => <RailCard key={p.id} product={p} />)}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function PromoSide({ banner }: { banner: PromoBanner }) {
  return (
    <Link
      href={banner.href}
      className={`group/side relative flex shrink-0 flex-col justify-between overflow-hidden rounded-2xl bg-gradient-to-br ${banner.tone} p-5 text-white lg:w-[288px]`}
    >
      {banner.src && (
        <Image
          src={banner.src}
          alt={banner.title}
          fill
          unoptimized
          sizes="288px"
          className="absolute inset-0 object-cover opacity-40 transition-transform duration-500 group-hover/side:scale-105"
        />
      )}
      {/* faint sunburst nod to the drum motif */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full opacity-20"
        style={{
          background:
            "repeating-conic-gradient(from 0deg, rgba(255,255,255,0.9) 0deg 6deg, transparent 6deg 12deg)",
        }}
      />
      <div className="relative">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-white/80">Ưu đãi trong tuần</p>
        <h3 className="mt-2 font-heading text-2xl font-extrabold leading-tight drop-shadow-sm">
          {banner.title}
        </h3>
        <p className="mt-2 max-w-[15rem] text-sm text-white/90">{banner.subtitle}</p>
      </div>
      <span className="relative mt-6 inline-flex w-fit items-center gap-1 rounded-full bg-white px-4 py-2 text-sm font-extrabold text-brand-800 shadow-md transition-transform group-hover/side:translate-x-0.5">
        {banner.cta}
        <ChevronRight className="h-4 w-4" />
      </span>
    </Link>
  );
}

function RailArrow({
  side,
  hidden,
  onClick,
}: {
  side: "left" | "right";
  hidden: boolean;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={side === "left" ? "Trượt về trước" : "Trượt tiếp"}
      onClick={onClick}
      className={`absolute top-1/2 z-10 hidden h-9 w-9 -translate-y-1/2 place-items-center rounded-full bg-card text-brand-700 shadow-lg ring-1 ring-border transition-all hover:scale-110 md:grid ${
        side === "left" ? "-left-3" : "-right-3"
      } ${hidden ? "pointer-events-none opacity-0" : "opacity-100"}`}
    >
      {side === "left" ? <ChevronLeft className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
    </button>
  );
}

function RailCard({ product }: { product: Product }) {
  const discount = Math.round(
    (1 - Number(product.sale_price) / Number(product.original_price)) * 100,
  );
  const sold = Math.max(product.review_count, 100 - product.stock_quantity * 5);
  return (
    <Link
      href={`/products/${product.slug}`}
      className="group/card flex w-[188px] shrink-0 flex-col rounded-xl border border-border bg-card p-3 transition-all duration-200 hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg"
    >
      <span className="mb-2 w-fit rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-bold text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
        Trả chậm 0% · trả trước 0₫
      </span>
      <div className="relative overflow-hidden rounded-lg">
        <ProductImage
          src={product.image_url}
          alt={product.name}
          sizes="188px"
          className="aspect-square"
        />
        <div className="absolute left-1.5 top-1.5 flex flex-col gap-1">
          {discount > 0 && (
            <span className="rounded-md bg-destructive px-1.5 py-0.5 text-[11px] font-bold text-white shadow">
              -{discount}%
            </span>
          )}
        </div>
        {product.inverter && (
          <span className="absolute right-1.5 top-1.5 rounded-md bg-accent px-1.5 py-0.5 text-[10px] font-bold text-accent-foreground shadow">
            Inverter
          </span>
        )}
      </div>

      <p className="mt-2.5 line-clamp-2 min-h-[2.5rem] text-xs font-semibold leading-5 text-foreground group-hover/card:text-primary">
        {product.name}
      </p>

      <p className="mt-1.5 text-base font-extrabold text-destructive">
        {formatPrice(product.sale_price)}
      </p>
      {discount > 0 && (
        <div className="mt-0.5 flex items-center gap-1.5 text-[11px]">
          <span className="text-muted-foreground line-through">
            {formatPrice(product.original_price)}
          </span>
          <span className="font-bold text-success">-{discount}%</span>
        </div>
      )}

      <div className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground">
        <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
        <span className="font-semibold text-foreground">{product.rating}</span>
        <span>· Đã bán {sold.toLocaleString("vi-VN")}</span>
      </div>
    </Link>
  );
}
