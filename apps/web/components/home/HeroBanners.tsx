import Link from "next/link";
import { BannerCarousel } from "@/components/home/BannerCarousel";
import { BannerImage } from "@/components/home/BannerImage";
import { heroBanners, sideBanners } from "@/lib/banners";

export function HeroBanners() {
  return (
    <section className="container pt-6">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <BannerCarousel banners={heroBanners} aspectClass="aspect-[16/8] sm:aspect-[16/7]" />
        <div className="hidden grid-rows-2 gap-4 lg:grid">
          {sideBanners.map((b) => (
            <Link key={b.src} href={b.href} className="group block">
              <BannerImage banner={b} className="h-full w-full rounded-2xl shadow-card" />
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
