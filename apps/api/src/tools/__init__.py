"""MCP-compatible tools (ADR A5, docs/pipelines.md §6.5).

Pipeline stages (S4) call these directly; only the `hỏi_chi_tiết_SP` branch
lets the LLM pick a tool itself via its JSON schema (hermes tool parser).
Currently implements `price_promo_stock`; `catalog_search`, `policy_faq`,
`review_summary` and `need_profile` are separate, later work.
"""

from src.tools.price_promo_stock import (
    PRICE_PROMO_STOCK_SCHEMA,
    Fact,
    PricePromoStockTool,
    ProductFacts,
)

__all__ = [
    "PRICE_PROMO_STOCK_SCHEMA",
    "Fact",
    "PricePromoStockTool",
    "ProductFacts",
]
