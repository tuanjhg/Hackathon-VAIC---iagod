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
from src.eval.golden import load_canonical, load_golden, write_normalized
from src.eval.judge import JudgeResult, judge_conversation
from src.eval.replay import replay_conversation
from src.eval.structural import ConversationReport, aggregate, classify_conversation
from src.models import Product
from src.router.client import LLMRouter
from src.seed.seed_realdata import seed_realdata
from src.services.advisor_chat_service import _get_policy_pipeline


def _find_repo_root() -> Path:
    """Find the nearest runtime root containing ``data``.

    A source checkout places this module at ``apps/api/src/eval`` while the
    container installs it at ``/app/src/eval``.  Looking for the actual data
    directory keeps the eval CLI portable across both layouts.
    """
    source = Path(__file__).resolve()
    for parent in source.parents:
        if (parent / "data").is_dir():
            return parent
    raise RuntimeError(f"Could not locate repository data directory from {source}")


REPO = _find_repo_root()
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
    conversations = (
        load_canonical(Path(args.dataset)) if args.dataset else load_golden(DATA_DIR)
    )
    print(f"loaded {len(conversations)} golden conversations")

    if args.conversation_id:
        conversations = [
            conversation
            for conversation in conversations
            if conversation.id == args.conversation_id
        ]
        if not conversations:
            raise SystemExit(f"conversation id not found: {args.conversation_id}")

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
                conversation,
                db=db,
                router=router,
                policy_search=policy_search,
                max_turns=args.max_turns,
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
    criteria = sorted({key for judgement in judgements for key in judgement.business_checks})
    criterion_pass_pct: dict[str, float] = {}
    total_passed = 0
    total_applicable = 0
    for criterion in criteria:
        rubric_values = [
            j.business_checks[criterion]
            for j in judgements
            if j.business_checks.get(criterion) is not None
        ]
        if rubric_values:
            passed = sum(1 for value in rubric_values if value is True)
            criterion_pass_pct[criterion] = round(100 * passed / len(rubric_values), 1)
            total_passed += passed
            total_applicable += len(rubric_values)
    return {
        "n_judged": len(judgements),
        "mean_scores": means,
        "business_pass_pct": (
            round(100 * total_passed / total_applicable, 1) if total_applicable else None
        ),
        "business_passed": total_passed,
        "business_applicable": total_applicable,
        "criterion_pass_pct": criterion_pass_pct,
    }


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
            row["business_checks"] = judged.business_checks
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
             "| id | source | golden | engaged | rec | kinds | overall | business |",
             "|---|---|---|---|---|---|---|---|"]
    for row in detail:
        src = str(row["source"]).split("_")[0][:10]
        raw_scores = row.get("judge_scores")
        overall = raw_scores.get("overall", "-") if isinstance(raw_scores, dict) else "-"
        raw_checks = row.get("business_checks")
        if isinstance(raw_checks, dict):
            applicable = [value for value in raw_checks.values() if value is not None]
            business = f"{sum(value is True for value in applicable)}/{len(applicable)}"
        else:
            business = "-"
        lines.append(
            f"| {row['id']} | {src} | {row['golden_category']} | {row['engaged_category']} "
            f"| {'Y' if row['recommended'] else 'N'} | {row['turn_kinds']} "
            f"| {overall} | {business} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden-conversation eval")
    parser.add_argument("--limit", type=int, default=5, help="conversations to sample")
    parser.add_argument("--all", action="store_true", help="run every conversation")
    parser.add_argument("--judge", action="store_true", help="also run the LLM judge")
    parser.add_argument("--seed", type=int, default=0, help="sampling seed")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=4,
        help="maximum user turns replayed per conversation (default: 4)",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="cached SQLite catalog path")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="report output dir")
    parser.add_argument(
        "--dataset",
        help="canonical JSON dataset; use a privacy-reviewed synthetic set for cloud LLM runs",
    )
    parser.add_argument("--conversation-id", help="run one exact conversation id")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
