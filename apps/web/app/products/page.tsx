import type { Metadata } from "next";
import { ProductsBrowser } from "@/components/ProductsBrowser";
import type { ProductFilters } from "@/types";

export const metadata: Metadata = {
  title: "Sản phẩm máy lạnh",
  description: "Duyệt catalog máy lạnh với bộ lọc theo giá, thương hiệu, diện tích phòng và inverter.",
};

type SearchParams = {
  search?: string;
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
    brand: params.brand,
    room_area: params.room_area ? Number(params.room_area) : undefined,
    max_price: params.max_price ? Number(params.max_price) : undefined,
    inverter: params.inverter === "true" ? true : undefined,
  };

  return (
    <div className="container py-10">
      <p className="font-bold text-primary">CATALOG</p>
      <h1 className="mt-2 font-heading text-3xl font-extrabold">Máy lạnh cho mọi không gian</h1>
      <p className="mt-3 max-w-2xl text-muted-foreground">
        Dữ liệu giá, tồn kho và thông số được cung cấp từ backend API.
      </p>
      <div className="mt-8">
        <ProductsBrowser initialFilters={initialFilters} />
      </div>
    </div>
  );
}
