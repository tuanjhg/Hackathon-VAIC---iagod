"""MCP-compatible tools (ADR A5, docs/pipelines.md §6.5).

Pipeline stages (S4) call these directly; only the `hỏi_chi_tiết_SP` branch
lets the LLM pick a tool itself via its JSON schema (hermes tool parser).
Currently implements `price_promo_stock` and `catalog_search` (structured-first
hard filter only — hybrid vector rerank is separate, ablation-gated work);
`policy_faq`, `review_summary` and `need_profile` (as a tool) are later work.
"""

from src.tools.catalog_search import TOOL_SCHEMA as CATALOG_SEARCH_SCHEMA
from src.tools.catalog_search import CatalogSearchResult, catalog_count, catalog_search
from src.tools.price_promo_stock import (
    PRICE_PROMO_STOCK_SCHEMA,
    Fact,
    PricePromoStockTool,
    ProductFacts,
)

__all__ = [
    "CATALOG_SEARCH_SCHEMA",
    "PRICE_PROMO_STOCK_SCHEMA",
    "CatalogSearchResult",
    "Fact",
    "PricePromoStockTool",
    "ProductFacts",
    "catalog_count",
    "catalog_search",
]
