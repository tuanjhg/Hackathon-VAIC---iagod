import Link from "next/link";
import { Mail, MapPin, Phone, Snowflake } from "lucide-react";

const COLUMNS = [
  {
    title: "Sản phẩm",
    links: [
      ["Tất cả máy lạnh", "/products"],
      ["Máy lạnh Inverter", "/products?inverter=true"],
      ["So sánh sản phẩm", "/compare"],
      ["Giỏ hàng", "/cart"],
    ],
  },
  {
    title: "Thương hiệu",
    links: [
      ["Daikin", "/products?brand=Daikin"],
      ["Panasonic", "/products?brand=Panasonic"],
      ["LG", "/products?brand=LG"],
      ["Samsung", "/products?brand=Samsung"],
    ],
  },
  {
    title: "Hỗ trợ",
    links: [
      ["Chính sách bảo hành", "#"],
      ["Giao hàng & lắp đặt", "#"],
      ["Trả góp 0%", "#"],
      ["Câu hỏi thường gặp", "#"],
    ],
  },
];

export function Footer() {
  return (
    <footer className="mt-16 border-t border-border bg-muted/40">
      <div className="container grid gap-10 py-14 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <p className="flex items-center gap-2 font-heading text-lg font-extrabold">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white">
              <Snowflake className="h-5 w-5" />
            </span>
            NeedWise <span className="text-accent">Copilot</span>
          </p>
          <p className="mt-4 max-w-xs text-sm leading-6 text-muted-foreground">
            Tư vấn máy lạnh dựa trên nhu cầu thật, dữ liệu minh bạch từ catalog. Thông tin thiếu được
            ghi rõ “Chưa có dữ liệu”.
          </p>
          <div className="mt-5 space-y-2 text-sm text-muted-foreground">
            <p className="flex items-center gap-2">
              <Phone className="h-4 w-4 text-primary" /> 1900 1234
            </p>
            <p className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-primary" /> hotro@needwise.vn
            </p>
            <p className="flex items-center gap-2">
              <MapPin className="h-4 w-4 text-primary" /> Hệ thống 128 cửa hàng toàn quốc
            </p>
          </div>
        </div>

        {COLUMNS.map((col) => (
          <div key={col.title}>
            <p className="font-heading font-bold text-foreground">{col.title}</p>
            <div className="mt-4 grid gap-2.5 text-sm text-muted-foreground">
              {col.links.map(([label, href]) => (
                <Link key={label} href={href} className="w-fit hover:text-foreground">
                  {label}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-border">
        <div className="container flex flex-col items-center justify-between gap-3 py-5 text-xs text-muted-foreground sm:flex-row">
          <p>© 2026 NeedWise Copilot — Demo AI-native commerce.</p>
          <div className="flex items-center gap-2">
            <span>Hỗ trợ thanh toán:</span>
            {["VISA", "MC", "MOMO", "VNPAY"].map((m) => (
              <span
                key={m}
                className="rounded-md border border-border bg-card px-2 py-1 text-[10px] font-bold text-foreground"
              >
                {m}
              </span>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}
