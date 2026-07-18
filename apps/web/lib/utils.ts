import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }
export function formatPrice(value: string | number) {
  const price = Number(value);
  return price > 0 ? `${new Intl.NumberFormat("vi-VN").format(price)} ₫` : "Liên hệ";
}

export function stockLabel(status: string) {
  if (status === "in_stock") return "Còn hàng";
  if (status === "low_stock") return "Sắp hết";
  if (status === "out_of_stock") return "Hết hàng";
  return "Chưa có dữ liệu tồn kho";
}
