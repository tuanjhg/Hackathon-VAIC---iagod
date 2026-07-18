import type { Category, ChatContext, ChatResponse, Comparison, Product, ProductFilters, ProductPage } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...options, headers: { "Content-Type": "application/json", ...options?.headers } });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Không thể kết nối máy chủ");
  return response.json() as Promise<T>;
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
};
