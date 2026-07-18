import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Product } from "@/types";

export interface CartItem { product: Product; quantity: number }
interface CartState { items: CartItem[]; add: (product: Product) => void; remove: (id: number) => void; setQuantity: (id: number, quantity: number) => void; clear: () => void }
export const useCartStore = create<CartState>()(persist((set) => ({
  items: [],
  add: (product) => set((state) => ({ items: state.items.some((item) => item.product.id === product.id) ? state.items.map((item) => item.product.id === product.id ? { ...item, quantity: item.quantity + 1 } : item) : [...state.items, { product, quantity: 1 }] })),
  remove: (id) => set((state) => ({ items: state.items.filter((item) => item.product.id !== id) })),
  setQuantity: (id, quantity) => set((state) => ({ items: quantity <= 0 ? state.items.filter((item) => item.product.id !== id) : state.items.map((item) => item.product.id === id ? { ...item, quantity } : item) })),
  clear: () => set({ items: [] }),
}), { name: "needwise-cart-real-catalog-v1" }));
