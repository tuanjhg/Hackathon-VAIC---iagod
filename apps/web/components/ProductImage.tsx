"use client";
import Image from "next/image";
import { ImageOff } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Product image. Currently pinned to a single static asset (`/sanpham.jpg`)
 * for every product — the `src` prop is accepted for API compatibility but
 * intentionally ignored. Restore `src={src}` below to wire real image URLs.
 */
const STATIC_PRODUCT_IMAGE = "/sanpham.jpg";

export function ProductImage({
  alt,
  priority = false,
  sizes = "(max-width: 768px) 100vw, 33vw",
  className,
}: {
  src?: string | null;
  alt: string;
  priority?: boolean;
  sizes?: string;
  className?: string;
}) {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  return (
    <div className={cn("relative aspect-[4/3] w-full overflow-hidden bg-muted", className)}>
      {status !== "error" && (
        <Image
          src={STATIC_PRODUCT_IMAGE}
          alt={alt}
          fill
          unoptimized
          priority={priority}
          sizes={sizes}
          onLoad={() => setStatus("ready")}
          onError={() => setStatus("error")}
          className={cn(
            "object-cover transition-[opacity,transform] duration-500 group-hover:scale-[1.03]",
            status === "ready" ? "opacity-100" : "opacity-0",
          )}
        />
      )}
      {status === "loading" && (
        <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-muted to-border" />
      )}
      {status === "error" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-muted to-border p-3 text-center text-muted-foreground">
          <ImageOff className="h-7 w-7 opacity-70" />
          <span className="line-clamp-2 text-[11px] font-medium leading-tight">{alt}</span>
        </div>
      )}
    </div>
  );
}
