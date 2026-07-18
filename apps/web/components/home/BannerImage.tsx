"use client";
import { ImageIcon } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import type { Banner } from "@/lib/banners";

/**
 * Renders a real banner image when the file exists under /public, otherwise a
 * styled gradient placeholder (so the layout looks intentional before assets
 * are added). Drop a file at `banner.src` and it appears automatically.
 */
export function BannerImage({ banner, className }: { banner: Banner; className?: string }) {
  const [ok, setOk] = useState(false);

  return (
    <div className={cn("group relative overflow-hidden bg-gradient-to-br", banner.tone, className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- optional user asset, graceful 404 */}
      <img
        src={banner.src}
        alt={banner.alt}
        onLoad={() => setOk(true)}
        onError={() => setOk(false)}
        className={cn(
          "absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-105",
          ok ? "opacity-100" : "opacity-0",
        )}
      />
      {!ok && (
        <div className="absolute inset-0 grid place-items-center p-4 text-center">
          <div className="text-white/90">
            <ImageIcon className="mx-auto h-7 w-7 opacity-80" />
            <p className="mt-2 text-sm font-bold leading-snug">{banner.alt}</p>
            <p className="mt-1 text-[11px] font-medium text-white/60">
              Thả ảnh: public{banner.src}
            </p>
          </div>
        </div>
      )}
      <div className="pointer-events-none absolute inset-0 rounded-[inherit] ring-1 ring-inset ring-black/10" />
    </div>
  );
}
