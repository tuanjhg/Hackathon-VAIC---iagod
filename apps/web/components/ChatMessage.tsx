"use client";
import { AlertTriangle, Ban, Bot, BookOpen, CheckCircle2, Info, ShieldCheck } from "lucide-react";
import { motion } from "framer-motion";
import { RecommendationCard } from "@/components/RecommendationCard";
import { AdvisorCard } from "@/components/AdvisorCard";
import type { ChatEntry } from "@/stores/chat-store";

const RESPONSE_LABELS: Partial<Record<NonNullable<ChatEntry["responseType"]>, string>> = {
  clarification: "Đang làm rõ nhu cầu",
  policy: "Thông tin chính sách",
  no_results: "Chưa tìm thấy lựa chọn phù hợp",
  handoff: "Cần kênh hỗ trợ chính thức",
  out_of_scope: "Ngoài phạm vi tư vấn",
  unsupported: "Chức năng chưa được hỗ trợ",
  error: "Kết nối đang gián đoạn",
};

export function ChatMessage({
  message,
  onQuickReply,
}: {
  message: ChatEntry;
  onQuickReply: (value: string) => void;
}) {
  const assistant = message.role === "assistant";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className={`flex gap-2 ${assistant ? "justify-start" : "justify-end"}`}
    >
      {assistant && (
        <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
          <Bot className="h-4 w-4" />
        </span>
      )}
      <div className={`max-w-[85%] ${assistant ? "" : "flex flex-col items-end"}`}>
        {assistant && message.responseType && RESPONSE_LABELS[message.responseType] && (
          <div className="mb-1.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            <Info className="h-3 w-3" />
            {RESPONSE_LABELS[message.responseType]}
          </div>
        )}

        {message.content && (
          <p
            className={
              assistant
                ? "rounded-2xl rounded-bl-sm bg-muted px-3.5 py-2.5 text-sm leading-5 text-foreground whitespace-pre-line"
                : "rounded-2xl rounded-br-sm bg-primary px-3.5 py-2.5 text-sm leading-5 text-primary-foreground"
            }
          >
            {message.content}
          </p>
        )}

        {message.quickReplies && message.quickReplies.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.quickReplies.map((reply) => (
              <button
                key={reply}
                onClick={() => onQuickReply(reply)}
                className="rounded-full border border-primary/40 bg-card px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary/10"
              >
                {reply}
              </button>
            ))}
          </div>
        )}

        {message.recommendations && message.recommendations.length > 0 && (
          <div className="mt-2 grid gap-2">
            {message.recommendations.map((item) => (
              <RecommendationCard key={item.product.id} item={item} />
            ))}
          </div>
        )}

        {message.cards && message.cards.length > 0 && (
          <div className="mt-2 grid gap-2">
            {message.cards.map((item) => (
              <AdvisorCard key={item.sku} item={item} />
            ))}
          </div>
        )}

        {message.antiPick && (
          <div className="mt-2 rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 text-xs leading-5 text-foreground">
            <div className="flex items-center gap-1.5 font-semibold text-rose-700 dark:text-rose-300">
              <Ban className="h-3.5 w-3.5" />
              Không nên chọn trong nhu cầu này
            </div>
            <p className="mt-1 font-semibold">{message.antiPick.name}</p>
            {message.antiPick.reason && (
              <p className="mt-0.5 text-muted-foreground">{message.antiPick.reason}</p>
            )}
          </div>
        )}

        {assistant && message.verifierFlags && message.verifierFlags.length > 0 && (
          <div className="mt-2 flex items-start gap-1.5 rounded-lg bg-amber-500/10 px-2.5 py-2 text-[11px] leading-4 text-amber-800 dark:text-amber-200">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            Nội dung đã được tự động điều chỉnh theo dữ liệu nguồn trước khi hiển thị.
          </div>
        )}

        {assistant && message.sourcePanel && message.sourcePanel.length > 0 && (
          <details className="mt-2 rounded-xl border border-border bg-card px-3 py-2 text-xs">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 font-semibold text-foreground">
              {message.verifierFlags?.length ? (
                <BookOpen className="h-3.5 w-3.5 text-amber-600" />
              ) : (
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
              )}
              Nguồn dữ liệu ({message.sourcePanel.length})
            </summary>
            <div className="mt-2 grid gap-1.5 text-[11px] leading-4 text-muted-foreground">
              {message.sourcePanel.map((source, index) => (
                <div key={`${source.sku}-${source.field}-${source.dataset}-${index}`}>
                  <span className="font-medium text-foreground">{source.sku}</span>
                  {" · "}{source.field}{" · "}{source.dataset}
                  {source.fetched_at && <span>{" · cập nhật "}{source.fetched_at}</span>}
                </div>
              ))}
            </div>
          </details>
        )}

        {assistant && message.responseType === "recommendations" && !message.verifierFlags?.length && (
          <div className="mt-2 flex items-center gap-1.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Nội dung đã qua bước đối chiếu dữ liệu.
          </div>
        )}

      </div>
    </motion.div>
  );
}
