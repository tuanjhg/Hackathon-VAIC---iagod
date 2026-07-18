"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ChevronLeft, ChevronRight, Zap } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Countdown } from "@/components/home/Countdown";
import { ProductImage } from "@/components/ProductImage";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import type { Product } from "@/types";

export function FlashSale() {
  const { data, isLoading } = useQuery({
    queryKey: ["products", { sort: "price_asc", page_size: 40, flash: true }],
    queryFn: () => api.products({ sort: "price_asc", page_size: 40 }),
  });

  const items = (data?.items ?? [])
    .map((p) => ({ p, discount: discountOf(p) }))
    .filter(({ discount }) => discount > 0)
    .sort((a, b) => b.discount - a.discount);

  const trackRef = useRef<HTMLDivElement>(null);
  const [paused, setPaused] = useState(false);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);

  const updateEdges = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    setAtStart(el.scrollLeft <= 4);
    setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 4);
  }, []);

  const slide = useCallback((dir: 1 | -1) => {
    const el = trackRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    const step = el.clientWidth * 0.85;
    let target = el.scrollLeft + dir * step;
    if (dir === 1 && el.scrollLeft >= max - 4) target = 0; // loop back to start
    else target = Math.max(0, Math.min(max, target));
    animateScrollLeft(el, target);
  }, []);

  // Autoplay every 3.5s, paused on hover/focus and when reduced motion is on.
  useEffect(() => {
    if (paused || items.length === 0) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = setInterval(() => slide(1), 3500);
    return () => clearInterval(id);
  }, [paused, items.length, slide]);

  useEffect(() => updateEdges(), [items.length, updateEdges]);

  return (
    // Full-bleed: break out of the page container to the full viewport width.
    <section className="relative left-1/2 mt-10 w-screen -translate-x-1/2">
      <div className="bg-gradient-to-br from-brand-800 via-brand-700 to-brand-600 py-5 sm:py-6">
        <div className="mx-auto max-w-[1600px] px-4 sm:px-6 lg:px-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 text-white">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/15 ring-1 ring-white/20">
                <Zap className="h-5 w-5 fill-amber-300 text-amber-300" />
              </span>
              <div>
                <h2 className="font-heading text-xl font-extrabold leading-none tracking-tight sm:text-2xl">
                  FLASH SALE
                </h2>
                <p className="mt-1 text-xs text-brand-100">Giá sốc mỗi ngày · số lượng có hạn</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Countdown />
              <Link
                href="/products?sort=price_asc"
                className="hidden rounded-full bg-white/15 px-3.5 py-1.5 text-xs font-bold text-white ring-1 ring-white/20 transition-colors hover:bg-white/25 sm:inline-block"
              >
                Xem tất cả
              </Link>
            </div>
          </div>

          <div
            className="group relative mt-4"
            onMouseEnter={() => setPaused(true)}
            onMouseLeave={() => setPaused(false)}
            onFocusCapture={() => setPaused(true)}
            onBlurCapture={() => setPaused(false)}
          >
            <ArrowButton side="left" hidden={atStart} onClick={() => slide(-1)} />
            <ArrowButton side="right" hidden={atEnd && !isLoading} onClick={() => slide(1)} />

            <div
              ref={trackRef}
              onScroll={updateEdges}
              className="flex gap-3 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
            >
              {isLoading
                ? Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="w-44 shrink-0 sm:w-48">
                      <Skeleton className="aspect-square w-full rounded-xl bg-white/20" />
                      <Skeleton className="mt-2 h-4 w-full bg-white/20" />
                      <Skeleton className="mt-1.5 h-4 w-2/3 bg-white/20" />
                    </div>
                  ))
                : items.map(({ p, discount }) => <FlashCard key={p.id} product={p} discount={discount} />)}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ArrowButton({
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
      className={`absolute top-1/2 z-10 hidden h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-white text-brand-700 shadow-lg ring-1 ring-black/5 transition-all hover:scale-110 md:grid ${
        side === "left" ? "-left-3 lg:-left-5" : "-right-3 lg:-right-5"
      } ${hidden ? "pointer-events-none opacity-0" : "opacity-100"}`}
    >
      {side === "left" ? <ChevronLeft className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
    </button>
  );
}

function FlashCard({ product, discount }: { product: Product; discount: number }) {
  const sold = Math.min(95, Math.max(15, 100 - product.stock_quantity * 6));
  return (
    <Link
      href={`/products/${product.slug}`}
      className="w-44 shrink-0 overflow-hidden rounded-xl bg-card p-2.5 shadow-md transition-transform duration-200 hover:-translate-y-1 sm:w-48"
    >
      <div className="relative overflow-hidden rounded-lg">
        <ProductImage src={product.image_url} alt={product.name} sizes="192px" className="aspect-square" />
        <span className="absolute left-1.5 top-1.5 rounded-md bg-destructive px-1.5 py-0.5 text-[11px] font-bold text-white shadow">
          -{discount}%
        </span>
      </div>
      <p className="mt-2 line-clamp-2 min-h-8 text-xs font-semibold leading-4 text-foreground">
        {product.name}
      </p>
      <p className="mt-1 text-base font-extrabold text-destructive">{formatPrice(product.sale_price)}</p>
      {product.stock_quantity > 0 && (
        <>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-gradient-to-r from-amber-400 to-destructive transition-[width] duration-700"
              style={{ width: `${sold}%` }}
            />
          </div>
          <p className="mt-1 text-[11px] font-semibold text-muted-foreground">Còn {product.stock_quantity} suất</p>
        </>
      )}
    </Link>
  );
}

function discountOf(p: Product) {
  return Math.round((1 - Number(p.sale_price) / Number(p.original_price)) * 100);
}

/** Smoothly animate scrollLeft via rAF — works even where scrollBy({behavior})
 *  is unreliable, and honours prefers-reduced-motion by jumping instantly. */
function animateScrollLeft(el: HTMLElement, target: number, duration = 450) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.scrollLeft = target;
    return;
  }
  const start = el.scrollLeft;
  const dist = target - start;
  let t0: number | null = null;
  const step = (ts: number) => {
    if (t0 === null) t0 = ts;
    const p = Math.min(1, (ts - t0) / duration);
    const ease = 1 - Math.pow(1 - p, 3); // easeOutCubic
    el.scrollLeft = start + dist * ease;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
