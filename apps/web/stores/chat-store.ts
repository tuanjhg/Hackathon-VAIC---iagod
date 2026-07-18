import { create } from "zustand";
import type { ChatContext, Recommendation, AdvisorCard } from "@/types";

export interface ChatEntry { 
  role: "user" | "assistant"; 
  content: string; 
  quickReplies?: string[]; 
  recommendations?: Recommendation[];
  cards?: AdvisorCard[];
}

interface ChatState { 
  isOpen: boolean; 
  isLoading: boolean; 
  sessionId: string; 
  context: ChatContext; 
  messages: ChatEntry[]; 
  toggle: () => void; 
  open: () => void; 
  addMessage: (message: ChatEntry) => void; 
  updateLastMessage: (message: Partial<ChatEntry>) => void;
  setLoading: (value: boolean) => void; 
  setContext: (context: ChatContext) => void;
  resetChat: () => void;
}

const getInitialMessage = (): ChatEntry => ({
  role: "Xin chào, tôi là NeedWise Copilot. Hãy chia sẻ về nhu cầu mua sắm của bạn và tôi sẽ tư vấn ra 1 sản phẩm phù hợp.",
});

const generateSessionId = () => {
  if (typeof window !== "undefined" && window.crypto) {
    try {
      return window.crypto.randomUUID();
    } catch {
      // Fallback
    }
  }
  return Math.random().toString(36).substring(2, 15);
};

export const useChatStore = create<ChatState>((set) => ({
  isOpen: false,
  isLoading: false,
  sessionId: generateSessionId(),
  context: { budget_max: null, room_area_m2: null, priority: null },
  messages: [getInitialMessage()],
  toggle: () => set((state) => ({ isOpen: !state.isOpen })),
  open: () => set({ isOpen: true }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  updateLastMessage: (msg) => set((state) => {
    const next = [...state.messages];
    if (next.length > 0) {
      next[next.length - 1] = { ...next[next.length - 1], ...msg };
    }
    return { messages: next };
  }),
  setLoading: (isLoading) => set({ isLoading }),
  setContext: (context) => set({ context }),
  resetChat: () => set({
    sessionId: generateSessionId(),
    context: { budget_max: null, room_area_m2: null, priority: null },
    messages: [getInitialMessage()],
    isLoading: false,
  }),
}));


