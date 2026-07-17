import { beforeEach, describe, expect, it } from "vitest";
import { useComparisonStore } from "@/stores/comparison-store";
import { product } from "./fixtures";

describe("comparison store", () => { beforeEach(() => useComparisonStore.setState({ products: [] })); it("limits comparison to three unique products", () => { expect(useComparisonStore.getState().add(product)).toBe(true); expect(useComparisonStore.getState().add(product)).toBe(false); useComparisonStore.getState().add({ ...product, id: 2 }); useComparisonStore.getState().add({ ...product, id: 3 }); expect(useComparisonStore.getState().add({ ...product, id: 4 })).toBe(false); expect(useComparisonStore.getState().products).toHaveLength(3); }); });

