import type { Category, ChatContext, ChatResponse, ChatStreamEvent, Comparison, Product, ProductFilters, ProductPage } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...options, headers: { "Content-Type": "application/json", ...options?.headers } });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Không thể kết nối máy chủ");
  return response.json() as Promise<T>;
}

export interface ChatStreamHandlers {
  /** One S7-verified sentence at a time, in order. */
  onDelta: (text: string) => void;
  /** The complete ChatResponse — always fires last (also on JSON fallback). */
  onFinal: (response: ChatResponse) => void;
}

/**
 * Streaming chat call (docs/pipelines.md §3.10): POST with
 * `Accept: text/event-stream`, read the body as a stream and parse
 * `data: {...}` SSE events. Falls back transparently to plain JSON when the
 * server (or a proxy) answers with `application/json`.
 */
async function chatStream(
  sessionId: string,
  message: string,
  context: ChatContext,
  handlers: ChatStreamHandlers,
): Promise<void> {
  const response = await fetch(`${API_URL}/chat/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ session_id: sessionId, message, context }),
  });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Không thể kết nối máy chủ");

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/event-stream") || !response.body) {
    handlers.onFinal((await response.json()) as ChatResponse);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawFinal = false;

  const handleEvent = (raw: string) => {
    for (const line of raw.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const event = JSON.parse(line.slice(6)) as ChatStreamEvent;
      if (event.type === "delta") handlers.onDelta(event.text);
      else if (event.type === "final") { sawFinal = true; handlers.onFinal(event.response); }
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let separator = buffer.indexOf("\n\n");
    while (separator !== -1) {
      handleEvent(buffer.slice(0, separator));
      buffer = buffer.slice(separator + 2);
      separator = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) handleEvent(buffer);
  if (!sawFinal) throw new Error("Kết nối bị gián đoạn, bạn thử lại nhé");
}

export const api = {
  categories: () => request<Category[]>("/categories"),
  products: (filters: ProductFilters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
    return request<ProductPage>(`/products?${params}`);
  },
  product: (slug: string) => request<Product>(`/products/${slug}`),
  compare: (ids: number[]) => request<Comparison>("/compare", { method: "POST", body: JSON.stringify({ product_ids: ids }) }),
  chat: (sessionId: string, message: string, context: ChatContext) => request<ChatResponse>("/chat/messages", { method: "POST", body: JSON.stringify({ session_id: sessionId, message, context }) }),
  chatStream,
};
