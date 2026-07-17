import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProductCard } from "@/components/ProductCard";
import { product } from "./fixtures";

describe("ProductCard", () => { it("renders product data and missing noise fallback", () => { render(<ProductCard product={product}/>); expect(screen.getByText(product.name)).toBeInTheDocument(); expect(screen.getByText("9.000.000 ₫")).toBeInTheDocument(); expect(screen.getByText("Chưa có dữ liệu")).toBeInTheDocument(); }); });

