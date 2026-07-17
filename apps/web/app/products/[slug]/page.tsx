import type { Metadata } from "next";
import { ProductDetail } from "@/components/ProductDetail";
import type { Product } from "@/types";

/** Server base can differ from the browser URL (e.g. `api:8000` inside Docker).
 *  Prefer API_URL for server-to-server, fall back to the public one. */
const SERVER_API = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function fetchProduct(slug: string): Promise<Product | null> {
  try {
    const res = await fetch(`${SERVER_API}/products/${slug}`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return (await res.json()) as Product;
  } catch {
    return null; // networking unavailable at build/SSR time — degrade gracefully
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const product = await fetchProduct(slug);
  if (!product) return { title: "Chi tiết sản phẩm" };

  const title = `${product.name} — ${product.brand}`;
  const description = product.short_description || `${product.name} chính hãng, bảo hành ${product.warranty_months} tháng.`;
  return {
    title,
    description,
    openGraph: {
      title,
      description,
      images: product.image_url ? [{ url: product.image_url }] : undefined,
    },
  };
}

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ProductDetail slug={slug} />;
}
