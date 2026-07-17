"use client";
import Image from "next/image";
import Link from "next/link";
import { GitCompareArrows, ShoppingCart, Star } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { formatPrice, stockLabel } from "@/lib/utils";
import { useCartStore } from "@/stores/cart-store";
import { useComparisonStore } from "@/stores/comparison-store";
import type { Product } from "@/types";

export function ProductCard({ product }: { product: Product }) {
  const addCart = useCartStore((state) => state.add);
  const addCompare = useComparisonStore((state) => state.add);
  const isOut = product.stock_status === "out_of_stock";
  return <article className="group flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card transition hover:-translate-y-0.5 hover:border-brand-200">
    <Link href={`/products/${product.slug}`} className="relative aspect-[4/3] overflow-hidden bg-slate-50"><Image src={product.image_url} alt={product.name} fill unoptimized sizes="(max-width: 768px) 100vw, 33vw" className="object-cover transition group-hover:scale-[1.02]"/>{product.promotion && <span className="absolute left-3 top-3 rounded-full bg-red-500 px-2.5 py-1 text-xs font-bold text-white">{product.promotion.title}</span>}</Link>
    <div className="flex flex-1 flex-col p-4"><div className="flex items-center justify-between"><span className="text-xs font-bold uppercase tracking-wide text-brand-600">{product.brand}</span><span className="flex items-center gap-1 text-xs"><Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400"/>{product.rating} ({product.review_count})</span></div>
      <Link href={`/products/${product.slug}`} className="mt-2 min-h-12 font-bold leading-6 text-slate-900 hover:text-brand-600">{product.name}</Link>
      <div className="mt-3"><span className="text-lg font-black text-red-600">{formatPrice(product.sale_price)}</span><span className="ml-2 text-xs text-slate-400 line-through">{formatPrice(product.original_price)}</span></div>
      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs text-slate-600"><div>{product.capacity_btu.toLocaleString("vi-VN")} BTU</div><div>{product.recommended_area_min}–{product.recommended_area_max} m²</div><div>{product.inverter ? "✓ Inverter" : "Không inverter"}</div><div>{product.noise_db === null ? "Chưa có dữ liệu" : `${product.noise_db} dB`}</div></dl>
      <p className={`mt-3 text-xs font-semibold ${isOut ? "text-red-600" : "text-emerald-600"}`}>{stockLabel(product.stock_status)}</p>
      <div className="mt-auto grid grid-cols-2 gap-2 pt-4"><Button variant="outline" size="sm" asChild><Link href={`/products/${product.slug}`}>Chi tiết</Link></Button><Button size="sm" disabled={isOut} onClick={() => { addCart(product); toast.success("Đã thêm vào giỏ hàng"); }}><ShoppingCart className="h-4 w-4"/>Thêm giỏ</Button><Button className="col-span-2" variant="ghost" size="sm" onClick={() => { const before = useComparisonStore.getState().products; if (addCompare(product)) toast.success("Đã thêm vào so sánh"); else toast.error(before.length >= 3 ? "Chỉ so sánh tối đa 3 sản phẩm" : "Sản phẩm đã có trong so sánh"); }}><GitCompareArrows className="h-4 w-4"/>Thêm so sánh</Button></div>
    </div>
  </article>;
}
