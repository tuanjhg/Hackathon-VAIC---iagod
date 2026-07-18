"""Golden-conversation eval runner: ``python -m src.eval.run_eval``.

Seeds a throwaway SQLite catalog from the 14 real categories, replays a sample
of golden conversations through the live pipeline (Tier 1 structural), optionally
scores each with the LLM judge (Tier 2), and writes a JSON + Markdown report.

Examples::

    python -m src.eval.run_eval --limit 5              # tier 1 on 5 convs
    python -m src.eval.run_eval --limit 5 --judge      # + LLM judge
    python -m src.eval.run_eval --all --judge          # full run (slow, costs LLM)

The real LLM is used for both replay (S2/S6) and the judge, so runs cost
OpenRouter calls — default is a small sample. The seeded DB is cached in the
temp dir and reused across runs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.core.database import Base
from src.eval.golden import load_golden, write_normalized
from src.eval.judge import JudgeResult, judge_conversation
from src.eval.replay import replay_conversation
from src.eval.structural import ConversationReport, aggregate, classify_conversation
from src.models import Product
from src.router.client import LLMRouter
from src.seed.seed_realdata import seed_realdata
from src.services.advisor_chat_service import _get_policy_pipeline

REPO = Path(__file__).resolve().parents[4]
DATA_DIR = REPO / "data"
PROCESSED_DIR = DATA_DIR / "realdata" / "processed"
DEFAULT_DB = Path(tempfile.gettempdir()) / "needwise_eval.db"
DEFAULT_OUT = DATA_DIR / "golden"


def _ensure_seeded_db(db_path: Path) -> sessionmaker:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        count = db.scalar(select(func.count()).select_from(Product)) or 0
        if count == 0:
            print(f"seeding catalog from {PROCESSED_DIR} …")
            created = seed_realdata(db, PROCESSED_DIR)
            print(f"  seeded {created} products")
        else:
            print(f"reusing cached catalog ({count} products) at {db_path}")
    return factory


async def _run(args: argparse.Namespace) -> None:
    conversations = load_golden(DATA_DIR)
    print(f"loaded {len(conversations)} golden conversations")

    out_dir = Path(args.out)
    write_normalized(conversations, out_dir / "normalized_conversations.json")

    if not args.all:
        random.seed(args.seed)
        conversations = random.sample(conversations, min(args.limit, len(conversations)))
        print(f"sampling {len(conversations)} conversations (seed={args.seed})")

    factory = _ensure_seeded_db(Path(args.db))
    router = LLMRouter()
    policy_search = _get_policy_pipeline()

    reports: list[ConversationReport] = []
    judgements: list[JudgeResult] = []
    started = time.perf_counter()

    for i, conversation in enumerate(conversations, 1):
        with factory() as db:
            replayed = await replay_conversation(
                conversation, db=db, router=router, policy_search=policy_search
            )
        report = classify_conversation(replayed)
        reports.append(report)
        line = (
            f"[{i}/{len(conversations)}] {conversation.id:8} "
            f"golden={report.golden_category} engaged={report.engaged_category} "
            f"rec={'Y' if report.recommended else 'N'} kinds={report.turn_kinds}"
        )
        if args.judge:
            judged = await judge_conversation(replayed, router=router)
            judgements.append(judged)
            line += f" scores={judged.scores}"
        print(line)

    elapsed = round(time.perf_counter() - started, 1)
    summary = aggregate(reports)
    if judgements:
        summary["judge"] = _judge_summary(judgements)
    summary["elapsed_seconds"] = elapsed

    _write_report(out_dir, summary, reports, judgements)
    print(f"\n=== SUMMARY ({elapsed}s) ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _judge_summary(judgements: list[JudgeResult]) -> dict[str, object]:
    dims = ("helpfulness", "grounding", "scope_handling", "overall")
    means: dict[str, float] = {}
    for dim in dims:
        values = [j.scores[dim] for j in judgements if dim in j.scores]
        if values:
            means[dim] = round(sum(values) / len(values), 2)
    return {"n_judged": len(judgements), "mean_scores": means}


def _write_report(
    out_dir: Path,
    summary: dict[str, object],
    reports: list[ConversationReport],
    judgements: list[JudgeResult],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    scores_by_id = {j.conversation_id: j for j in judgements}
    detail = []
    for report in reports:
        row = asdict(report)
        judged = scores_by_id.get(report.id)
        if judged is not None:
            row["judge_scores"] = judged.scores
            row["judge_rationale"] = judged.rationale
        detail.append(row)

    (out_dir / "eval_report.json").write_text(
        json.dumps({"summary": summary, "conversations": detail}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "eval_report.md").write_text(_markdown(summary, detail), encoding="utf-8")
    print(f"wrote report -> {out_dir / 'eval_report.md'}")


def _markdown(summary: dict[str, object], detail: list[dict[str, object]]) -> str:
    lines = ["# Golden-conversation eval report", "", "## Summary", "```json",
             json.dumps(summary, ensure_ascii=False, indent=2), "```", "",
             "## Per-conversation", "",
             "| id | source | golden | engaged | rec | kinds | overall |",
             "|---|---|---|---|---|---|---|"]
    for row in detail:
        src = str(row["source"]).split("_")[0][:10]
        raw_scores = row.get("judge_scores")
        overall = raw_scores.get("overall", "-") if isinstance(raw_scores, dict) else "-"
        lines.append(
            f"| {row['id']} | {src} | {row['golden_category']} | {row['engaged_category']} "
            f"| {'Y' if row['recommended'] else 'N'} | {row['turn_kinds']} "
            f"| {overall} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden-conversation eval")
    parser.add_argument("--limit", type=int, default=5, help="conversations to sample")
    parser.add_argument("--all", action="store_true", help="run every conversation")
    parser.add_argument("--judge", action="store_true", help="also run the LLM judge")
    parser.add_argument("--seed", type=int, default=0, help="sampling seed")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="cached SQLite catalog path")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="report output dir")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
