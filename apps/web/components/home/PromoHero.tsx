import Link from "next/link";
import { ArrowRight, Snowflake, Sparkles, Wallet } from "lucide-react";
import { HeroChatButton } from "@/components/HeroChatButton";

export function PromoHero() {
  return (
    <section className="container pt-6">
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Main banner */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-brand-900 via-brand-700 to-brand-600 p-8 text-white lg:col-span-2 lg:p-10">
          <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-accent/25 blur-3xl" />
          <div className="pointer-events-none absolute bottom-0 right-8 opacity-20">
            <Snowflake className="h-48 w-48" />
          </div>
          <div className="relative max-w-md">
            <span className="inline-flex animate-fade-up items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-bold ring-1 ring-white/25">
              <Sparkles className="h-3.5 w-3.5 text-accent" />
              MÙA NÓNG 2026
            </span>
            <h1
              className="mt-4 animate-fade-up font-heading text-3xl font-extrabold leading-tight sm:text-4xl"
              style={{ animationDelay: "0.08s" }}
            >
              Máy lạnh chính hãng
              <br />
              giảm đến <span className="text-cyan-300">40%</span>
            </h1>
            <p className="mt-3 animate-fade-up text-brand-100" style={{ animationDelay: "0.16s" }}>
              Trả góp 0% · Giao lắp miễn phí · Bảo hành tận nhà.
            </p>
            <div className="mt-6 flex animate-fade-up flex-wrap gap-3" style={{ animationDelay: "0.24s" }}>
              <Link
                href="/products"
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-white px-5 text-sm font-bold text-brand-700 transition-transform hover:scale-[1.02]"
              >
                Mua ngay <ArrowRight className="h-4 w-4" />
              </Link>
              <HeroChatButton />
            </div>
          </div>
        </div>

        {/* Side cards */}
        <div className="grid gap-4">
          <Link
            href="/products"
            className="group relative flex flex-col justify-between overflow-hidden rounded-3xl bg-gradient-to-br from-accent to-cyan-600 p-6 text-white"
          >
            <div>
              <Sparkles className="h-7 w-7" />
              <h2 className="mt-3 font-heading text-xl font-bold">Chưa biết chọn gì?</h2>
              <p className="mt-1 text-sm text-white/90">Để AI tư vấn theo diện tích & ngân sách.</p>
            </div>
            <span className="mt-4 inline-flex items-center gap-1 text-sm font-bold">
              Hỏi trợ lý AI
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </span>
          </Link>
          <div className="flex items-center gap-3 rounded-3xl border border-border bg-card p-6 shadow-card">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-success/15 text-success">
              <Wallet className="h-6 w-6" />
            </span>
            <div>
              <h2 className="font-heading font-bold">Trả góp 0%</h2>
              <p className="text-sm text-muted-foreground">Duyệt nhanh qua thẻ, kỳ hạn đến 12 tháng.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
