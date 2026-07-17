"use client";
import Link from "next/link";
import { Menu, Search, ShoppingCart, X } from "lucide-react";
import { useState } from "react";
import { useCartStore } from "@/stores/cart-store";
import { useComparisonStore } from "@/stores/comparison-store";

export function Header() {
  const [open, setOpen] = useState(false);
  const cartCount = useCartStore((state) => state.items.reduce((sum, item) => sum + item.quantity, 0));
  const compareCount = useComparisonStore((state) => state.products.length);
  const nav = [["Trang chủ", "/"], ["Sản phẩm", "/products"], [`So sánh (${compareCount})`, "/compare"], [`Giỏ hàng (${cartCount})`, "/cart"]];
  return <header className="sticky top-0 z-40 border-b bg-white/95 backdrop-blur">
    <div className="container flex h-16 items-center gap-5">
      <Link href="/" className="shrink-0 text-xl font-black tracking-tight text-brand-700">NeedWise <span className="text-emerald-500">Copilot</span></Link>
      <form action="/products" className="relative hidden max-w-lg flex-1 md:block"><Search className="absolute left-3 top-2.5 h-5 w-5 text-slate-400"/><input name="search" aria-label="Tìm kiếm" placeholder="Tìm máy lạnh, thương hiệu..." className="h-10 w-full rounded-xl border bg-slate-50 pl-10 pr-4 outline-none focus:border-brand-500"/></form>
      <nav className="ml-auto hidden items-center gap-5 lg:flex">{nav.map(([label, href]) => <Link key={href} href={href} className="text-sm font-medium text-slate-600 hover:text-brand-600">{label}</Link>)}</nav>
      <Link href="/cart" aria-label="Giỏ hàng" className="relative lg:hidden"><ShoppingCart/><span className="absolute -right-2 -top-2 rounded-full bg-brand-600 px-1.5 text-[10px] text-white">{cartCount}</span></Link>
      <button aria-label="Menu" className="lg:hidden" onClick={() => setOpen(!open)}>{open ? <X/> : <Menu/>}</button>
    </div>
    {open && <nav className="container grid gap-3 border-t py-4 lg:hidden">{nav.map(([label, href]) => <Link key={href} href={href} onClick={() => setOpen(false)}>{label}</Link>)}</nav>}
  </header>;
}

