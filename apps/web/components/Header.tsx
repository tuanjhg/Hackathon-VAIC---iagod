"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { GitCompareArrows, Menu, Search, ShoppingCart, Snowflake, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useCartStore } from "@/stores/cart-store";
import { useComparisonStore } from "@/stores/comparison-store";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { cn } from "@/lib/utils";

const NAV = [
  { label: "Trang chủ", href: "/" },
  { label: "Sản phẩm", href: "/products" },
];

/** Store counts are hydrated from localStorage on the client only; gate on
 *  `mounted` so server HTML (0) matches first client render, avoiding mismatch. */
function useMounted() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

export function Header() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const mounted = useMounted();
  const cartCount = useCartStore((s) => s.items.reduce((sum, i) => sum + i.quantity, 0));
  const compareCount = useComparisonStore((s) => s.products.length);

  useEffect(() => setOpen(false), [pathname]);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="container flex h-16 items-center gap-4">
        <Link href="/" className="flex shrink-0 items-center gap-2 font-heading text-xl font-extrabold tracking-tight">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white">
            <Snowflake className="h-5 w-5" />
          </span>
          <span className="text-foreground">
            NeedWise<span className="text-accent"> Copilot</span>
          </span>
        </Link>

        <form action="/products" className="relative hidden max-w-md flex-1 md:block">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            name="search"
            aria-label="Tìm kiếm sản phẩm"
            placeholder="Tìm máy lạnh, thương hiệu…"
            className="h-10 w-full rounded-xl border border-input bg-muted/60 pl-10 pr-4 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:bg-card focus-visible:ring-2 focus-visible:ring-ring/35"
          />
        </form>

        <nav className="ml-auto hidden items-center gap-1 lg:flex">
          {NAV.map(({ label, href }) => (
            <NavLink key={href} href={href} active={pathname === href}>
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1.5 lg:ml-2">
          <IconLink href="/compare" label="So sánh" count={mounted ? compareCount : 0} active={pathname === "/compare"}>
            <GitCompareArrows className="h-5 w-5" />
          </IconLink>
          <IconLink href="/cart" label="Giỏ hàng" count={mounted ? cartCount : 0} active={pathname === "/cart"}>
            <ShoppingCart className="h-5 w-5" />
          </IconLink>
          <ThemeToggle />
          <button
            aria-label="Menu"
            aria-expanded={open}
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-foreground hover:bg-muted lg:hidden"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {open && (
          <motion.nav
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden border-t border-border lg:hidden"
          >
            <div className="container grid gap-1 py-3">
              <form action="/products" className="relative mb-2">
                <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  name="search"
                  aria-label="Tìm kiếm sản phẩm"
                  placeholder="Tìm máy lạnh, thương hiệu…"
                  className="h-11 w-full rounded-xl border border-input bg-muted/60 pl-10 pr-4 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/35"
                />
              </form>
              {NAV.map(({ label, href }) => (
                <Link
                  key={href}
                  href={href}
                  className="rounded-xl px-3 py-2.5 text-sm font-semibold text-foreground hover:bg-muted"
                >
                  {label}
                </Link>
              ))}
            </div>
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  );
}

function NavLink({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-xl px-3 py-2 text-sm font-semibold transition-colors",
        active ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {children}
    </Link>
  );
}

function IconLink({
  href,
  label,
  count,
  active,
  children,
}: {
  href: string;
  label: string;
  count: number;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-label={`${label}${count ? ` (${count})` : ""}`}
      className={cn(
        "relative inline-flex h-9 w-9 items-center justify-center rounded-xl transition-colors",
        active ? "bg-primary/10 text-primary" : "text-foreground hover:bg-muted",
      )}
    >
      {children}
      {count > 0 && (
        <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[10px] font-bold text-accent-foreground">
          {count}
        </span>
      )}
    </Link>
  );
}
