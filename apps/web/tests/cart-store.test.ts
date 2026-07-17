import { beforeEach, describe, expect, it } from "vitest";
import { useCartStore } from "@/stores/cart-store";
import { product } from "./fixtures";

describe("cart store", () => { beforeEach(() => useCartStore.setState({ items: [] })); it("adds and changes quantity", () => { useCartStore.getState().add(product); useCartStore.getState().add(product); expect(useCartStore.getState().items[0].quantity).toBe(2); useCartStore.getState().setQuantity(product.id, 1); expect(useCartStore.getState().items[0].quantity).toBe(1); }); });

