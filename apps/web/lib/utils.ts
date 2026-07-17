import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }
export function formatPrice(value: string | number) { return `${new Intl.NumberFormat("vi-VN").format(Number(value))} ₫`; }
export function stockLabel(status: string) { return status === "in_stock" ? "Còn hàng" : status === "low_stock" ? "Sắp hết" : "Hết hàng"; }

