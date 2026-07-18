# Golden-conversation eval report

## Summary
```json
{
  "total": 3,
  "by_source": {
    "35sample_chat_history (1).json": 3
  },
  "recommended_convs": 1,
  "recommended_pct": 33.3,
  "engaged_supported_category_convs": 1,
  "convs_with_error_turn": 3,
  "turn_kind_distribution": {
    "unsupported": 17,
    "out_of_scope": 12,
    "error": 6,
    "recommend": 3,
    "ask": 2
  },
  "golden_intent_buckets": {
    "non_product": 2,
    "in_catalog_supported": 1
  },
  "supported_categories": [
    "may_lanh",
    "may_nuoc_nong",
    "tu_lanh",
    "tu_mat_dong"
  ],
  "judge": {
    "n_judged": 3,
    "mean_scores": {
      "helpfulness": 1.0,
      "grounding": 2.0,
      "scope_handling": 1.0,
      "overall": 1.0
    }
  },
  "elapsed_seconds": 285.6
}
```

## Per-conversation

| id | source | golden | engaged | rec | kinds | overall |
|---|---|---|---|---|---|---|
| f1-25 | 35sample | None | None | N | {'error': 3, 'unsupported': 2, 'out_of_scope': 2} | - |
| f1-27 | 35sample | may_lanh | may_lanh | Y | {'unsupported': 14, 'ask': 2, 'out_of_scope': 6, 'recommend': 3, 'error': 1} | 1 |
| f1-3 | 35sample | None | None | N | {'error': 2, 'out_of_scope': 4, 'unsupported': 1} | 1 |
