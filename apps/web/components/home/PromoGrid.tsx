import Link from "next/link";
import { BannerImage } from "@/components/home/BannerImage";
import { SectionHeader } from "@/components/home/SectionHeader";
import { promoBanners } from "@/lib/banners";

export function PromoGrid() {
  return (
    <section className="container pt-12">
      <SectionHeader eyebrow="ƯU ĐÃI" title="Gian hàng ưu đãi" href="/products" />
      <div className="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {promoBanners.map((b) => (
          <Link
            key={b.src}
            href={b.href}
            className="block overflow-hidden rounded-2xl shadow-card transition-transform duration-300 hover:-translate-y-1"
          >
            <BannerImage banner={b} className="aspect-[3/4]" />
          </Link>
        ))}
      </div>
    </section>
  );
}
