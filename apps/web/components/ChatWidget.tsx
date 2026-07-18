"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, Send, Sparkles, X, RotateCcw } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chat-store";
import { ChatMessage } from "@/components/ChatMessage";

export function ChatWidget() {
  const {
    isOpen,
    isLoading,
    messages,
    sessionId,
    context,
    toggle,
    addMessage,
    updateLastMessage,
    setLoading,
    setContext,
    resetChat,
  } = useChatStore();
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [messages, isLoading]);

  const send = async (text: string) => {
    const value = text.trim();
    if (!value || isLoading) return;
    addMessage({ role: "user", content: value });
    setInput("");
    setLoading(true);

    // Add an empty assistant message which we will fill during streaming
    addMessage({ role: "assistant", content: "" });

    let accumulatedText = "";
    try {
      await api.chatStream(sessionId, value, context, {
        onDelta: (deltaText: string) => {
          if (accumulatedText) {
            accumulatedText += " " + deltaText;
          } else {
            accumulatedText = deltaText;
          }
          updateLastMessage({ content: accumulatedText });
        },
        onFinal: (response) => {
          setContext(response.context);
          updateLastMessage({
            content: response.message,
            quickReplies: response.quick_replies,
            recommendations: response.recommendations,
            cards: response.cards,
          });
        },
      });
    } catch (err) {
      console.error("Streaming failed, falling back to unary:", err);
      try {
        const response = await api.chat(sessionId, value, context);
        setContext(response.context);
        updateLastMessage({
          content: response.message,
          quickReplies: response.quick_replies,
          recommendations: response.recommendations,
          cards: response.cards,
        });
      } catch (fallbackErr) {
        console.error("Fallback also failed:", fallbackErr);
        updateLastMessage({
          content: "Mình chưa kết nối được máy chủ. Bạn thử lại sau nhé.",
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(input);
  };

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end">
      <AnimatePresence>
        {isOpen && (
          <motion.section
            key="chat-panel"
            aria-label="Chat tư vấn"
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 320, damping: 28 }}
            className="mb-3 flex h-[min(640px,calc(100vh-110px))] w-[min(390px,calc(100vw-32px))] flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-2xl"
          >
            <header className="flex items-center gap-3 bg-gradient-to-r from-brand-700 to-brand-600 p-4 text-white">
              <span className="grid h-10 w-10 place-items-center rounded-full bg-white/15 ring-1 ring-white/25">
                <Bot className="h-5 w-5" />
              </span>
              <div className="flex-1">
                <h2 className="font-heading font-bold">NeedWise Copilot</h2>
                <p className="flex items-center gap-1 text-xs text-brand-100">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
                  Tư vấn theo nhu cầu thật
                </p>
              </div>
              <button
                aria-label="Làm mới cuộc trò chuyện"
                title="Làm mới cuộc trò chuyện"
                className="grid h-8 w-8 place-items-center rounded-full text-white/90 transition-colors hover:bg-white/15 mr-1"
                onClick={resetChat}
              >
                <RotateCcw className="h-4.5 w-4.5" />
              </button>
              <button
                aria-label="Đóng chat"
                className="grid h-8 w-8 place-items-center rounded-full text-white/90 transition-colors hover:bg-white/15"
                onClick={toggle}
              >
                <X className="h-5 w-5" />
              </button>
            </header>

            <div className="flex-1 space-y-3 overflow-y-auto bg-background/50 p-3">
              {messages.map((message, index) => (
                <ChatMessage key={index} message={message} onQuickReply={(v) => void send(v)} />
              ))}
              {isLoading && <TypingIndicator />}
              <div ref={bottom} />
            </div>

            <form onSubmit={submit} className="flex items-center gap-2 border-t border-border p-3">
              <input
                aria-label="Tin nhắn"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="VD: Phòng 18m²…"
                className="h-11 flex-1 rounded-xl border border-input bg-background px-3.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/35"
              />
              <button
                aria-label="Gửi"
                disabled={!input.trim() || isLoading}
                className="grid h-11 w-11 place-items-center rounded-xl bg-primary text-primary-foreground transition-all hover:brightness-110 disabled:opacity-50"
              >
                <Send className="h-5 w-5" />
              </button>
            </form>
          </motion.section>
        )}
      </AnimatePresence>

      <button
        aria-label={isOpen ? "Đóng chatbot" : "Mở chatbot"}
        onClick={toggle}
        className="group flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-brand-600 to-accent text-white shadow-xl shadow-brand-600/30 transition-transform hover:scale-105 active:scale-95"
      >
        {isOpen ? (
          <X className="h-6 w-6" />
        ) : (
          <span className="relative">
            <Sparkles className="h-6 w-6" />
            <span className="absolute -right-1.5 -top-1.5 h-2.5 w-2.5 animate-ping rounded-full bg-white/80" />
          </span>
        )}
      </button>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-2">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
        <Bot className="h-4 w-4" />
      </span>
      <span className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-muted px-4 py-3">
        {[0, 0.15, 0.3].map((delay) => (
          <span
            key={delay}
            className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/60"
            style={{ animationDelay: `${delay}s` }}
          />
        ))}
      </span>
    </div>
  );
}
