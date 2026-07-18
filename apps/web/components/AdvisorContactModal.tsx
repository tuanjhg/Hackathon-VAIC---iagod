"use client";
import { Headphones, Phone, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AdvisorContactModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] grid place-items-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Gặp tư vấn viên"
        className="w-[min(360px,calc(100vw-32px))] rounded-3xl border border-border bg-card p-6 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
            <Headphones className="h-5 w-5" />
          </span>
          <button
            aria-label="Đóng"
            className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-muted"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <h2 className="mt-3 font-heading text-lg font-bold text-foreground">Gặp tư vấn viên</h2>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Cần hỗ trợ thêm ngoài AI? Đội ngũ tư vấn viên hỗ trợ 24/7, sẵn sàng giúp bạn qua hotline.
        </p>
        <Button asChild size="lg" className="mt-4 w-full">
          <a href="tel:19001234">
            <Phone className="h-4 w-4" />
            Gọi 1900 1234
          </a>
        </Button>
      </div>
    </div>
  );
}
