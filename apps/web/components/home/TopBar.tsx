import { MapPin, Phone, ShieldCheck, Truck } from "lucide-react";

export function TopBar() {
  return (
    <div className="hidden border-b border-border bg-muted/50 text-xs text-muted-foreground md:block">
      <div className="container flex h-9 items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <Truck className="h-3.5 w-3.5 text-primary" />
            Giao lắp miễn phí nội thành
          </span>
          <span className="flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-success" />
            Bảo hành chính hãng tận nhà
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <MapPin className="h-3.5 w-3.5" />
            Hệ thống 128 cửa hàng
          </span>
          <a href="tel:19001234" className="flex items-center gap-1.5 font-semibold text-foreground hover:text-primary">
            <Phone className="h-3.5 w-3.5" />
            1900 1234
          </a>
        </div>
      </div>
    </div>
  );
}
