import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Product } from "@/types";

interface ComparisonState { products: Product[]; add: (product: Product) => boolean; remove: (id: number) => void; clear: () => void }
export const useComparisonStore = create<ComparisonState>()(persist((set, get) => ({
  products: [],
  add: (product) => { const products = get().products; if (products.some((item) => item.id === product.id) || products.length >= 3) return false; set({ products: [...products, product] }); return true; },
  remove: (id) => set((state) => ({ products: state.products.filter((item) => item.id !== id) })),
  clear: () => set({ products: [] }),
}), { name: "needwise-comparison-real-catalog-v1" }));
