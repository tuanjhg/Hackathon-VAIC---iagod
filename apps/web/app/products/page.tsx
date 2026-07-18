import type { Metadata } from "next";
import { ProductsBrowser } from "@/components/ProductsBrowser";
import type { ProductFilters } from "@/types";

export const metadata: Metadata = {
  title: "Catalog sản phẩm",
  description: "Duyệt 8.746 sản phẩm thực tế thuộc 14 ngành hàng.",
};

type SearchParams = {
  search?: string;
  category?: string;
  brand?: string;
  room_area?: string;
  max_price?: string;
  inverter?: string;
};

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const initialFilters: ProductFilters = {
    search: params.search,
    category: params.category,
    brand: params.brand,
    room_area: params.room_area ? Number(params.room_area) : undefined,
    max_price: params.max_price ? Number(params.max_price) : undefined,
    inverter: params.inverter === "true" ? true : undefined,
  };

  return (
    <div className="container py-10">
      <p className="font-bold text-primary">CATALOG</p>
      <h1 className="mt-2 font-heading text-3xl font-extrabold">8.746 sản phẩm từ catalog thực tế</h1>
      <p className="mt-3 max-w-2xl text-muted-foreground">
        Dữ liệu thuộc 14 ngành hàng được đọc từ PostgreSQL qua backend API. Các trường chưa có trong nguồn được hiển thị rõ ràng.
      </p>
      <div className="mt-8">
        <ProductsBrowser initialFilters={initialFilters} />
      </div>
    </div>
  );
}
