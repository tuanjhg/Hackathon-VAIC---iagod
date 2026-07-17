"use client";
import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { BannerImage } from "@/components/home/BannerImage";
import { cn } from "@/lib/utils";
import type { Banner } from "@/lib/banners";

export function BannerCarousel({
  banners,
  aspectClass = "aspect-[16/7]",
}: {
  banners: Banner[];
  aspectClass?: string;
}) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const n = banners.length;

  const go = useCallback((dir: 1 | -1) => setIndex((p) => (p + dir + n) % n), [n]);

  useEffect(() => {
    if (paused || n <= 1) return;
    const id = setInterval(() => setIndex((p) => (p + 1) % n), 4500);
    return () => clearInterval(id);
  }, [paused, n]);

  return (
    <div
      className={cn("group relative overflow-hidden rounded-2xl shadow-card", aspectClass)}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div
        className="flex h-full transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
        style={{ transform: `translateX(-${index * 100}%)` }}
      >
        {banners.map((b) => (
          <Link key={b.src} href={b.href} className="relative block h-full w-full shrink-0">
            <BannerImage banner={b} className="h-full w-full" />
          </Link>
        ))}
      </div>

      {n > 1 && (
        <>
          <CarouselArrow side="left" onClick={() => go(-1)} />
          <CarouselArrow side="right" onClick={() => go(1)} />
          <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5">
            {banners.map((b, i) => (
              <button
                key={b.src}
                aria-label={`Chuyển tới banner ${i + 1}`}
                aria-current={i === index}
                onClick={() => setIndex(i)}
                className={cn(
                  "h-2 rounded-full bg-white transition-all",
                  i === index ? "w-6 opacity-100" : "w-2 opacity-50 hover:opacity-80",
                )}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function CarouselArrow({ side, onClick }: { side: "left" | "right"; onClick: () => void }) {
  return (
    <button
      aria-label={side === "left" ? "Banner trước" : "Banner sau"}
      onClick={onClick}
      className={cn(
        "absolute top-1/2 z-10 hidden h-10 w-10 -translate-y-1/2 place-items-center rounded-full bg-white/85 text-brand-700 shadow-lg backdrop-blur transition-all hover:bg-white group-hover:opacity-100 md:grid md:opacity-0",
        side === "left" ? "left-3" : "right-3",
      )}
    >
      {side === "left" ? <ChevronLeft className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
    </button>
  );
}
