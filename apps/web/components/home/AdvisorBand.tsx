import { MessagesSquare, ListChecks, Sparkles } from "lucide-react";
import { HeroChatButton } from "@/components/HeroChatButton";

const STEPS = [
  { icon: MessagesSquare, title: "Mô tả nhu cầu", desc: "Diện tích phòng, ngân sách, ưu tiên của bạn." },
  { icon: ListChecks, title: "AI phân tích", desc: "Đối chiếu catalog thật, lọc theo tiêu chí cứng." },
  { icon: Sparkles, title: "Nhận 3 gợi ý", desc: "Kèm lý do, điểm mạnh và đánh đổi rõ ràng." },
];

export function AdvisorBand() {
  return (
    // Full-bleed dark "spotlight" band for the AI advisor feature.
    <section className="relative left-1/2 mt-12 w-screen -translate-x-1/2 overflow-hidden bg-gradient-to-br from-[#0a1a33] via-brand-900 to-[#0b2a4a] text-white">
      <div className="pointer-events-none absolute -left-16 top-1/2 h-72 w-72 -translate-y-1/2 rounded-full bg-accent/20 blur-3xl" />
      <div className="pointer-events-none absolute -right-10 -top-16 h-72 w-72 rounded-full bg-brand-500/25 blur-3xl" />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.15]"
        style={{
          backgroundImage:
            "radial-gradient(rgba(255,255,255,0.6) 1px, transparent 1px)",
          backgroundSize: "26px 26px",
        }}
      />

      <div className="relative mx-auto max-w-[1200px] px-4 py-12 sm:px-6 lg:px-10 lg:py-16">
        <div className="grid gap-10 lg:grid-cols-[1fr_1.15fr] lg:items-center">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent/20 px-3 py-1 text-xs font-bold text-accent ring-1 ring-accent/30">
              <Sparkles className="h-3.5 w-3.5" />
              TRỢ LÝ AI
            </span>
            <h2 className="mt-3 font-heading text-3xl font-extrabold leading-tight sm:text-4xl">
              Không chắc nên mua máy nào?
            </h2>
            <p className="mt-3 max-w-md text-brand-100">
              Trả lời vài câu hỏi, NeedWise gợi ý đúng máy lạnh cho nhu cầu thật của bạn — minh bạch,
              không bịa dữ liệu.
            </p>
            <div className="mt-6">
              <HeroChatButton />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, desc }, i) => (
              <div
                key={title}
                className="rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur-sm transition-colors hover:bg-white/[0.1]"
              >
                <div className="flex items-center gap-2">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent/20 text-accent">
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="font-heading text-xs font-bold text-brand-200">Bước {i + 1}</span>
                </div>
                <p className="mt-2.5 font-heading font-bold">{title}</p>
                <p className="mt-1 text-sm leading-5 text-brand-100/80">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
