"use client";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, LoaderCircle, PackageSearch } from "lucide-react";
import { ProductCard } from "@/components/ProductCard";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { ProductFilters } from "@/types";

export function ProductGrid({ filters = {}, limit }: { filters?: ProductFilters; limit?: number }) {
  const queryFilters = { ...filters, page_size: limit ?? filters.page_size };
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["products", queryFilters], queryFn: () => api.products(queryFilters) });
  if (isLoading) return <div className="state-box"><LoaderCircle className="animate-spin text-brand-600"/>Đang tải sản phẩm...</div>;
  if (error) return <div className="state-box text-red-600"><AlertCircle/>Không tải được sản phẩm.<Button variant="outline" onClick={() => refetch()}>Thử lại</Button></div>;
  if (!data?.items.length) return <div className="state-box"><PackageSearch/>Không tìm thấy sản phẩm phù hợp.</div>;
  return <div><div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{data.items.map((product) => <ProductCard key={product.id} product={product}/>)}</div>{!limit && <p className="mt-6 text-center text-sm text-slate-500">Hiển thị {data.items.length} / {data.total} sản phẩm</p>}</div>;
}

