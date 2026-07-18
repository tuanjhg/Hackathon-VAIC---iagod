import Link from "next/link";
import { ArrowRight, Home, Maximize, Sofa } from "lucide-react";

const ROOMS = [
  { icon: Home, title: "Phòng nhỏ", desc: "Dưới 15 m² · 9.000 BTU", href: "/products?room_area=12", tone: "from-sky-500 to-brand-600" },
  { icon: Sofa, title: "Phòng vừa", desc: "15–20 m² · 12.000 BTU", href: "/products?room_area=18", tone: "from-accent to-cyan-600" },
  { icon: Maximize, title: "Phòng lớn", desc: "20–30 m² · 18.000 BTU", href: "/products?room_area=25", tone: "from-brand-600 to-brand-800" },
];

const BRANDS = ["Daikin", "Panasonic", "LG", "Samsung", "Casper"];

export function ShopByNeed() {
  return (
    <section className="container pt-12">
      <div className="flex items-end justify-between">
        <div>
          <p className="font-bold text-primary">CHỌN NHANH</p>
          <h2 className="mt-1 font-heading text-2xl font-extrabold">Mua theo nhu cầu</h2>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-3">
        {ROOMS.map(({ icon: Icon, title, desc, href, tone }) => (
          <Link
            key={title}
            href={href}
            className={`group relative flex items-center gap-4 overflow-hidden rounded-2xl bg-gradient-to-br ${tone} p-5 text-white`}
          >
            <span className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-white/15 ring-1 ring-white/25">
              <Icon className="h-7 w-7" />
            </span>
            <div className="flex-1">
              <p className="font-heading text-lg font-bold">{title}</p>
              <p className="text-sm text-white/90">{desc}</p>
            </div>
            <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-1" />
          </Link>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="mr-1 text-sm font-semibold text-muted-foreground">Thương hiệu:</span>
        {BRANDS.map((brand) => (
          <Link
            key={brand}
            href={`/products?brand=${brand}`}
            className="rounded-full border border-border bg-card px-4 py-1.5 text-sm font-semibold text-foreground shadow-sm transition-colors hover:border-primary hover:text-primary"
          >
            {brand}
          </Link>
        ))}
      </div>
    </section>
  );
}
