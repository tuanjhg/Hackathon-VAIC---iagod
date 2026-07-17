import type { Metadata } from "next";
import { ComparisonTable } from "@/components/ComparisonTable";

export const metadata: Metadata = {
  title: "So sánh sản phẩm",
  description: "So sánh 2–3 máy lạnh cạnh nhau theo giá, công suất, độ ồn, bảo hành và khuyến mãi.",
};

export default function ComparePage() {
  return (
    <div className="container py-10">
      <p className="font-bold text-primary">ĐỐI CHIẾU RÕ RÀNG</p>
      <h1 className="mt-2 font-heading text-3xl font-extrabold">So sánh sản phẩm</h1>
      <p className="mt-3 max-w-2xl text-muted-foreground">
        Chọn từ 2 đến 3 máy lạnh để xem khác biệt quan trọng.
      </p>
      <div className="mt-8">
        <ComparisonTable />
      </div>
    </div>
  );
}
