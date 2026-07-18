"use client";
import Link from "next/link";
import { Minus, Plus, ShoppingBag, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StateBox } from "@/components/ui/state";
import { ProductImage } from "@/components/ProductImage";
import { formatPrice } from "@/lib/utils";
import { useCartStore } from "@/stores/cart-store";

export default function CartPage() {
  const items = useCartStore((s) => s.items);
  const remove = useCartStore((s) => s.remove);
  const setQuantity = useCartStore((s) => s.setQuantity);
  const total = items.reduce((sum, i) => sum + Number(i.product.sale_price) * i.quantity, 0);

  return (
    <div className="container py-10">
      <p className="font-bold text-primary">GIỎ HÀNG</p>
      <h1 className="mt-2 font-heading text-3xl font-extrabold">Sản phẩm bạn đã chọn</h1>

      {!items.length ? (
        <StateBox
          className="mt-8"
          icon={<ShoppingBag className="h-6 w-6" />}
          title="Giỏ hàng đang trống"
          description="Khám phá catalog để thêm máy lạnh phù hợp với nhu cầu của bạn."
          action={
            <Button asChild>
              <Link href="/products">Khám phá sản phẩm</Link>
            </Button>
          }
        />
      ) : (
        <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_340px]">
          <div className="space-y-3">
            {items.map(({ product, quantity }) => (
              <article
                key={product.id}
                className="flex gap-4 rounded-2xl border border-border bg-card p-4 shadow-card"
              >
                <Link href={`/products/${product.slug}`} className="w-28 shrink-0">
                  <ProductImage
                    src={product.image_url}
                    alt={product.name}
                    sizes="112px"
                    className="rounded-xl"
                  />
                </Link>
                <div className="min-w-0 flex-1">
                  <Link href={`/products/${product.slug}`} className="font-heading font-bold hover:text-primary">
                    {product.name}
                  </Link>
                  <p className="mt-1 font-extrabold text-destructive">{formatPrice(product.sale_price)}</p>
                  <div className="mt-3 flex items-center gap-1">
                    <button
                      aria-label="Giảm số lượng"
                      className="grid h-8 w-8 place-items-center rounded-lg border border-border transition-colors hover:bg-muted"
                      onClick={() => setQuantity(product.id, quantity - 1)}
                    >
                      <Minus className="h-4 w-4" />
                    </button>
                    <span className="w-9 text-center font-semibold">{quantity}</span>
                    <button
                      aria-label="Tăng số lượng"
                      className="grid h-8 w-8 place-items-center rounded-lg border border-border transition-colors hover:bg-muted"
                      onClick={() => setQuantity(product.id, quantity + 1)}
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </div>
                </div>
                <button
                  aria-label="Xóa"
                  onClick={() => remove(product.id)}
                  className="self-start text-muted-foreground transition-colors hover:text-destructive"
                >
                  <Trash2 className="h-5 w-5" />
                </button>
              </article>
            ))}
          </div>

          <aside className="h-fit rounded-2xl border border-border bg-card p-6 shadow-card lg:sticky lg:top-20">
            <h2 className="font-heading text-xl font-bold">Tóm tắt đơn hàng</h2>
            <div className="mt-5 flex justify-between text-sm">
              <span className="text-muted-foreground">Tạm tính</span>
              <strong>{formatPrice(total)}</strong>
            </div>
            <div className="mt-3 flex justify-between text-sm">
              <span className="text-muted-foreground">Phí vận chuyển</span>
              <strong className="text-success">Miễn phí</strong>
            </div>
            <div className="mt-5 flex justify-between border-t border-border pt-5 text-lg">
              <strong>Tổng cộng</strong>
              <strong className="text-destructive">{formatPrice(total)}</strong>
            </div>
            <Button
              className="mt-6 w-full"
              size="lg"
              onClick={() => toast.success("Checkout demo đã được ghi nhận")}
            >
              Checkout (demo)
            </Button>
            <p className="mt-3 text-center text-xs text-muted-foreground">
              Chưa phát sinh thanh toán thật.
            </p>
          </aside>
        </div>
      )}
    </div>
  );
}
