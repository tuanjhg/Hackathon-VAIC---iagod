"use client";
import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import { LoaderCircle, MessageCircle, ShieldCheck, ShoppingCart, Star } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatPrice, stockLabel } from "@/lib/utils";
import { useCartStore } from "@/stores/cart-store";
import { useChatStore } from "@/stores/chat-store";

export function ProductDetail({ slug }: { slug: string }) {
  const { data: product, isLoading, error } = useQuery({ queryKey: ["product", slug], queryFn: () => api.product(slug) });
  const add = useCartStore((state) => state.add); const openChat = useChatStore((state) => state.open);
  if (isLoading) return <div className="state-box"><LoaderCircle className="animate-spin"/>Đang tải chi tiết...</div>;
  if (error || !product) return <div className="state-box text-red-600">Không tìm thấy hoặc không tải được sản phẩm.</div>;
  const specs = [["Công suất", `${product.capacity_btu.toLocaleString("vi-VN")} BTU (${product.horsepower} HP)`], ["Diện tích phù hợp", `${product.recommended_area_min}–${product.recommended_area_max} m²`], ["Công nghệ", product.inverter ? "Inverter" : "Non-inverter"], ["Độ ồn", product.noise_db === null ? "Chưa có dữ liệu" : `${product.noise_db} dB`], ["Nhãn năng lượng", product.energy_rating], ["Bảo hành", `${product.warranty_months} tháng`]];
  return <div className="container py-10"><div className="grid gap-10 lg:grid-cols-2"><div className="relative aspect-[4/3] overflow-hidden rounded-3xl bg-slate-50"><Image src={product.image_url} alt={product.name} fill priority unoptimized className="object-cover"/></div><div><p className="font-bold uppercase tracking-wider text-brand-600">{product.brand}</p><h1 className="mt-2 text-3xl font-black leading-tight">{product.name}</h1><p className="mt-3 flex items-center gap-2 text-sm"><Star className="h-4 w-4 fill-amber-400 text-amber-400"/>{product.rating} · {product.review_count} đánh giá</p><div className="mt-6"><span className="text-3xl font-black text-red-600">{formatPrice(product.sale_price)}</span><span className="ml-3 text-slate-400 line-through">{formatPrice(product.original_price)}</span></div>{product.promotion && <div className="mt-4 rounded-xl border border-red-100 bg-red-50 p-3"><strong className="text-red-700">{product.promotion.title}</strong><p className="text-sm text-red-600">{product.promotion.description}</p></div>}<p className={`mt-4 font-semibold ${product.stock_quantity ? "text-emerald-600" : "text-red-600"}`}>{stockLabel(product.stock_status)} · {product.stock_quantity} sản phẩm</p><p className="mt-5 leading-7 text-slate-600">{product.short_description}</p><div className="mt-7 flex flex-wrap gap-3"><Button size="lg" disabled={!product.stock_quantity} onClick={() => { add(product); toast.success("Đã thêm vào giỏ hàng"); }}><ShoppingCart/>Thêm vào giỏ</Button><Button variant="outline" size="lg" onClick={openChat}><MessageCircle/>Hỏi chatbot</Button></div></div></div>
    <div className="mt-12 grid gap-8 lg:grid-cols-3"><section className="rounded-2xl border bg-white p-6 lg:col-span-2"><h2 className="text-xl font-bold">Thông số cơ bản</h2><dl className="mt-5 divide-y">{specs.map(([label, value]) => <div key={label} className="grid grid-cols-2 py-3 text-sm"><dt className="text-slate-500">{label}</dt><dd className="font-semibold">{value}</dd></div>)}</dl></section><div className="space-y-5"><section className="rounded-2xl border bg-emerald-50 p-6"><ShieldCheck className="text-emerald-600"/><h2 className="mt-3 font-bold">Chính sách bảo hành</h2><p className="mt-2 text-sm leading-6 text-slate-600">Bảo hành chính hãng {product.warranty_months} tháng. Hỗ trợ đổi mới theo điều kiện của nhà sản xuất.</p></section><section className="rounded-2xl border p-6"><h2 className="font-bold">Đánh giá gần đây</h2><p className="mt-3 text-sm italic text-slate-600">“Làm lạnh nhanh, giao lắp đúng hẹn. Thông tin tư vấn dễ hiểu.”</p><p className="mt-2 text-xs text-slate-400">— Khách hàng demo</p></section></div></div>
  </div>;
}
