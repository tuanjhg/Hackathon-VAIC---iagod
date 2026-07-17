import { BadgeCheck, Headphones, Truck, Wrench } from "lucide-react";

const ITEMS = [
  { icon: BadgeCheck, title: "Chính hãng 100%", desc: "Đầy đủ VAT, tem hãng" },
  { icon: Truck, title: "Giao lắp miễn phí", desc: "Nội thành trong 24h" },
  { icon: Wrench, title: "Bảo hành tận nhà", desc: "Kỹ thuật đến tận nơi" },
  { icon: Headphones, title: "Hỗ trợ 24/7", desc: "Hotline 1900 1234" },
];

export function TrustBar() {
  return (
    <section className="container pt-6">
      <div className="grid grid-cols-2 gap-3 rounded-2xl border border-border bg-card p-4 shadow-card md:grid-cols-4">
        {ITEMS.map(({ icon: Icon, title, desc }) => (
          <div key={title} className="flex items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
              <Icon className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-heading text-sm font-bold">{title}</p>
              <p className="truncate text-xs text-muted-foreground">{desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
