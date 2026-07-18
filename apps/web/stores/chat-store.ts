import { create } from "zustand";
import type { ChatContext, Recommendation } from "@/types";

export interface ChatEntry { role: "user" | "assistant"; content: string; quickReplies?: string[]; recommendations?: Recommendation[] }
interface ChatState { isOpen: boolean; isLoading: boolean; sessionId: string; context: ChatContext; messages: ChatEntry[]; toggle: () => void; open: () => void; addMessage: (message: ChatEntry) => void; setLoading: (value: boolean) => void; setContext: (context: ChatContext) => void; reset: () => void }

const initialContext: ChatContext = { budget_max: null, room_area_m2: null, priority: null, xung_ho: null };
const initialMessages: ChatEntry[] = [
  {
    role: "assistant",
    content:
      "Chào bạn 👋 Mình là NeedWise Copilot. Cho mình biết phòng của bạn và ưu tiên (mát nhanh, êm, tiết kiệm điện…) — mình sẽ gợi ý máy lạnh hợp nhất. Chọn nhanh một gợi ý bên dưới nhé:",
    quickReplies: ["Phòng ngủ 15m2", "Phòng khách 25m2", "Phòng nhỏ 12m2", "Phòng lớn 30m2"],
  },
];

function newSessionId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export const useChatStore = create<ChatState>((set) => ({
  isOpen: false, isLoading: false, sessionId: "demo-session", context: initialContext,
  messages: initialMessages,
  toggle: () => set((state) => ({ isOpen: !state.isOpen })), open: () => set({ isOpen: true }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  setLoading: (isLoading) => set({ isLoading }), setContext: (context) => set({ context }),
  reset: () =>
    set({
      sessionId: newSessionId(),
      context: initialContext,
      messages: initialMessages,
      isLoading: false,
    }),
}));

