import { create } from "zustand";
import type {
  AdvisorAntiPick,
  AdvisorCard,
  ChatContext,
  GuardrailMeta,
  ChatResponseType,
  Recommendation,
  ResponseAction,
  SourcePanelEntry,
  VerifierFlag,
} from "@/types";

export interface ChatEntry { 
  role: "user" | "assistant"; 
  content: string; 
  quickReplies?: string[]; 
  actions?: ResponseAction[];
  recommendations?: Recommendation[];
  cards?: AdvisorCard[];
  responseType?: ChatResponseType;
  intent?: string | null;
  antiPick?: AdvisorAntiPick | null;
  sourcePanel?: SourcePanelEntry[];
  verifierFlags?: VerifierFlag[];
  guardrail?: GuardrailMeta;
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
  role: "assistant",
  content: "Dạ em là NeedWise Copilot. Anh/chị hãy chia sẻ nhu cầu, ngân sách và không gian sử dụng; em sẽ làm rõ khi cần rồi đề xuất tối đa 3 lựa chọn cùng ưu điểm và đánh đổi ạ.",
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
