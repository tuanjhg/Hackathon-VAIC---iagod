import { create } from "zustand";
import type { ChatContext, Recommendation } from "@/types";

export interface ChatEntry { role: "user" | "assistant"; content: string; quickReplies?: string[]; recommendations?: Recommendation[] }
interface ChatState { isOpen: boolean; isLoading: boolean; sessionId: string; context: ChatContext; messages: ChatEntry[]; toggle: () => void; open: () => void; addMessage: (message: ChatEntry) => void; setLoading: (value: boolean) => void; setContext: (context: ChatContext) => void }
export const useChatStore = create<ChatState>((set) => ({
  isOpen: false, isLoading: false, sessionId: "demo-session", context: { budget_max: null, room_area_m2: null, priority: null },
  messages: [{ role: "assistant", content: "Chào bạn! Hãy cho mình biết diện tích phòng để bắt đầu nhé." }],
  toggle: () => set((state) => ({ isOpen: !state.isOpen })), open: () => set({ isOpen: true }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  setLoading: (isLoading) => set({ isLoading }), setContext: (context) => set({ context }),
}));

