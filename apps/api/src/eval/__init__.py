"""Golden-conversation evaluation harness for the advisory chatbot.

Two tiers (docs/research/dmx-data-eval-roi-plan.md D4 + llm-evaluation skill):

* **Tier 1 — structural coverage** (deterministic, no judge): replay each golden
  conversation's user turns through the live pipeline and classify what the bot
  did per turn (ask / recommend / out-of-scope / unsupported / …), the category
  it engaged, and whether it stayed on-scope vs the golden reference.
* **Tier 2 — LLM-as-judge** (reference-based): score the bot transcript against
  the golden transcript for helpfulness, grounding and appropriateness.

The golden set comes from ``data/`` — one valid JSON file and one structurally
malformed file that :mod:`src.eval.golden` repairs tolerantly.
"""
