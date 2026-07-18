"use client";
import { Bot } from "lucide-react";
import { motion } from "framer-motion";
import { RecommendationCard } from "@/components/RecommendationCard";
import { AdvisorCard } from "@/components/AdvisorCard";
import type { ChatEntry } from "@/stores/chat-store";

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

      </div>
    </motion.div>
  );
}
