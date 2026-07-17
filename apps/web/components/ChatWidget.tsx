"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, LoaderCircle, MessageCircle, Send, X } from "lucide-react";
import { api } from "@/lib/api";
import { useChatStore } from "@/stores/chat-store";
import { ChatMessage } from "@/components/ChatMessage";

export function ChatWidget() {
  const { isOpen, isLoading, messages, sessionId, context, toggle, addMessage, setLoading, setContext } = useChatStore();
  const [input, setInput] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = bottom.current;
    if (element && typeof element.scrollIntoView === "function") {
      element.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages, isLoading]);
  const send = async (text: string) => {
    const value = text.trim(); if (!value || isLoading) return;
    addMessage({ role: "user", content: value }); setInput(""); setLoading(true);
    try { const response = await api.chat(sessionId, value, context); setContext(response.context); addMessage({ role: "assistant", content: response.message, quickReplies: response.quick_replies, recommendations: response.recommendations }); }
    catch { addMessage({ role: "assistant", content: "Mình chưa kết nối được máy chủ. Bạn thử lại sau nhé." }); }
    finally { setLoading(false); }
  };
  const submit = (event: FormEvent) => { event.preventDefault(); void send(input); };
  return <div className="fixed bottom-5 right-5 z-50">
    {isOpen && <section aria-label="Chat tư vấn" className="mb-3 flex h-[min(640px,calc(100vh-110px))] w-[min(390px,calc(100vw-32px))] flex-col overflow-hidden rounded-2xl border bg-white shadow-2xl">
      <header className="flex items-center gap-3 bg-brand-700 p-4 text-white"><span className="rounded-full bg-white/15 p-2"><Bot/></span><div><h2 className="font-bold">NeedWise Copilot</h2><p className="text-xs text-brand-100">Tư vấn theo nhu cầu thật</p></div><button aria-label="Đóng chat" className="ml-auto" onClick={toggle}><X/></button></header>
      <div className="flex-1 space-y-3 overflow-y-auto p-3">{messages.map((message, index) => <ChatMessage key={index} message={message} onQuickReply={(value) => void send(value)}/>)}{isLoading && <div className="flex items-center gap-2 text-xs text-slate-500"><LoaderCircle className="h-4 w-4 animate-spin"/>Đang tìm lựa chọn phù hợp...</div>}<div ref={bottom}/></div>
      <form onSubmit={submit} className="flex gap-2 border-t p-3"><input aria-label="Tin nhắn" value={input} onChange={(e) => setInput(e.target.value)} placeholder="VD: Phòng 18m2..." className="input flex-1"/><button aria-label="Gửi" disabled={!input.trim() || isLoading} className="rounded-xl bg-brand-600 p-2.5 text-white disabled:opacity-50"><Send className="h-5 w-5"/></button></form>
    </section>}
    <button aria-label={isOpen ? "Đóng chatbot" : "Mở chatbot"} onClick={toggle} className="ml-auto flex h-14 w-14 items-center justify-center rounded-full bg-brand-600 text-white shadow-xl hover:bg-brand-700">{isOpen ? <X/> : <MessageCircle/>}</button>
  </div>;
}
