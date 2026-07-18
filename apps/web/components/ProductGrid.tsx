"use client";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { AlertCircle, ChevronLeft, ChevronRight, PackageSearch } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ProductCard, ProductCardSkeleton } from "@/components/ProductCard";
import { Button } from "@/components/ui/button";
import { Reveal } from "@/components/ui/reveal";
import { StateBox } from "@/components/ui/state";
import { api } from "@/lib/api";
import type { ProductFilters } from "@/types";

export function ProductGrid({ filters = {}, limit }: { filters?: ProductFilters; limit?: number }) {
  const [page, setPage] = useState(1);

  // Reset to first page whenever the filters (other than page) change.
  const filtersKey = useMemo(() => {
    const { page: _p, ...rest } = filters;
    void _p;
    return JSON.stringify(rest);
  }, [filters]);
  useEffect(() => setPage(1), [filtersKey]);

  const queryFilters = { ...filters, page: limit ? 1 : page, page_size: limit ?? filters.page_size };
  const { data, isLoading, isError, isPlaceholderData, refetch } = useQuery({
    queryKey: ["products", queryFilters],
    queryFn: () => api.products(queryFilters),
    placeholderData: keepPreviousData,
  });

  if (isLoading) {
    return (
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: limit ?? 6 }).map((_, i) => (
          <ProductCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <StateBox
        tone="danger"
        icon={<AlertCircle className="h-6 w-6" />}
        title="Không tải được sản phẩm"
        description="Có thể máy chủ đang bận. Bạn thử lại nhé."
        action={
          <Button variant="outline" onClick={() => refetch()}>
            Thử lại
          </Button>
        }
      />
    );
  }

  if (!data?.items.length) {
    return (
      <StateBox
        icon={<PackageSearch className="h-6 w-6" />}
        title="Không tìm thấy sản phẩm phù hợp"
        description="Thử nới lỏng bộ lọc hoặc từ khóa tìm kiếm."
      />
    );
  }

  return (
    <div>
      <div
        className={`grid gap-5 sm:grid-cols-2 xl:grid-cols-3 transition-opacity ${
          isPlaceholderData ? "opacity-60" : "opacity-100"
        }`}
      >
        {data.items.map((product, i) => (
          <Reveal key={product.id} delay={Math.min(i, 5) * 0.06} className="h-full">
            <ProductCard product={product} />
          </Reveal>
        ))}
      </div>

      {!limit && data.pages > 1 && (
        <Pagination page={data.page} pages={data.pages} onChange={setPage} />
      )}

      {!limit && (
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Hiển thị {data.items.length} / {data.total} sản phẩm
        </p>
      )}
    </div>
  );
}

function Pagination({
  page,
  pages,
  onChange,
}: {
  page: number;
  pages: number;
  onChange: (page: number) => void;
}) {
  const numbers = Array.from({ length: pages }, (_, i) => i + 1).filter(
    (n) => n === 1 || n === pages || Math.abs(n - page) <= 1,
  );

  return (
    <nav aria-label="Phân trang" className="mt-8 flex items-center justify-center gap-1.5">
      <Button
        variant="outline"
        size="icon"
        aria-label="Trang trước"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      {numbers.map((n, i) => (
        <span key={n} className="flex items-center gap-1.5">
          {i > 0 && n - numbers[i - 1] > 1 && <span className="px-1 text-muted-foreground">…</span>}
          <Button
            variant={n === page ? "default" : "outline"}
            size="icon"
            aria-label={`Trang ${n}`}
            aria-current={n === page ? "page" : undefined}
            onClick={() => onChange(n)}
          >
            {n}
          </Button>
        </span>
      ))}
      <Button
        variant="outline"
        size="icon"
        aria-label="Trang sau"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </nav>
  );
}
