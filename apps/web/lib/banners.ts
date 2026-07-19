export type Banner = {
  /** Path under /public. Drop a real image here to replace the placeholder. */
  src: string;
  alt: string;
  href: string;
  /** Placeholder gradient shown until a real image is dropped in. */
  tone: string;
};

export const heroBanners: Banner[] = [
  {
    src: "/banners/hero-1.jpg",
    alt: "Máy lạnh mùa nóng — giảm đến 40%",
    href: "/products",
    tone: "from-brand-800 via-brand-600 to-accent",
  },
  {
    src: "/banners/hero-2.jpg",
    alt: "Trả góp 0% — nhận ngay quà tặng",
    href: "/products?inverter=true",
    tone: "from-[#0a1a33] via-brand-800 to-brand-600",
  },
  {
    src: "/banners/hero-3.jpg",
    alt: "Tuần lễ thương hiệu Daikin",
    href: "/products?brand=Daikin",
    tone: "from-accent via-cyan-600 to-brand-700",
  },
];

export const sideBanners: Banner[] = [
  {
    src: "/banners/side-1.jpg",
    alt: "Ưu đãi máy Inverter tiết kiệm điện",
    href: "/products?inverter=true",
    tone: "from-emerald-600 to-teal-600",
  },
  {
    src: "/banners/side-2.jpg",
    alt: "Tuần lễ vàng Dreame — săn robot cùng CR7",
    href: "/products",
    tone: "from-indigo-600 to-brand-700",
  },
];

export const promoBanners: Banner[] = [
  { src: "/banners/promo-1.jpg", alt: "Tủ lạnh tranh cúp — giảm đến 7 triệu", href: "/products", tone: "from-sky-600 to-brand-700" },
  { src: "/banners/promo-2.jpg", alt: "Tháng LG — giảm đến 10 triệu", href: "/products?brand=LG", tone: "from-rose-600 to-red-700" },
  { src: "/banners/promo-3.jpg", alt: "Super sale online — deal cực chất", href: "/products?sort=price_asc", tone: "from-fuchsia-600 to-purple-700" },
  { src: "/banners/promo-4.jpg", alt: "Sale mạnh giải nhiệt — mát 0đ phí", href: "/products?inverter=true", tone: "from-amber-500 to-orange-600" },
];

export const subBanners: Banner[] = [
  { src: "/banners/sub-1.jpg", alt: "World Cup — bỏ nhỏ lấy tivi to", href: "/products", tone: "from-brand-700 to-brand-500" },
  { src: "/banners/sub-2.jpg", alt: "Tháng LG — trợ giá bỏ nhỏ lấy to", href: "/products?brand=LG", tone: "from-slate-800 to-brand-800" },
];
