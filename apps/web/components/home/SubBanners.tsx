import Link from "next/link";
import { BannerImage } from "@/components/home/BannerImage";
import { subBanners } from "@/lib/banners";

export function SubBanners() {
  return (
    <section className="container pt-12">
      <div className="grid gap-4 sm:grid-cols-2">
        {subBanners.map((b) => (
          <Link
            key={b.src}
            href={b.href}
            className="block overflow-hidden rounded-2xl shadow-card transition-transform duration-300 hover:-translate-y-1"
          >
            <BannerImage banner={b} className="aspect-[5/2]" />
          </Link>
        ))}
      </div>
    </section>
  );
}
