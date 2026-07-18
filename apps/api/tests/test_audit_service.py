"""Audit-log writer tests — SQLite in-memory, same pattern as other DB tests."""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.database import Base
from src.models import AuditLog
from src.pipeline.need_profile import NeedProfile
from src.pipeline.orchestrator import TurnResult
from src.pipeline.s8_respond import SourceEntry, VerifierFlag
from src.services.audit_service import write_audit_log
from src.verifier import ClaimVerdict, VerificationResult


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as db:
        yield db
    Base.metadata.drop_all(engine)


def _turn_result() -> TurnResult:
    profile = NeedProfile(category="may_lanh", slots={"ngan_sach_max": 15_000_000})
    return TurnResult(
        kind="recommend",
        message="[1] có độ ồn 29dB.",
        intent="tu_van",
        profile=profile,
        total_candidates=3,
        verification=VerificationResult(
            claims=[
                ClaimVerdict(kind="direct", verdict="match", sku="sku_a"),
                ClaimVerdict(kind="direct", verdict="mismatch", sku="sku_b"),
            ],
            per_claim_error_rate=0.5,
        ),
        verifier_flags=[VerifierFlag(action="corrected", sku="sku_b", field="noise_db_indoor")],
        source_panel=[SourceEntry(sku="sku_a", field="price", dataset="may_lanh")],
        regenerated=True,
        timings_ms={"s2": 400.0},
    )


def test_writes_turn_row_with_masked_message(session: Session) -> None:
    row = write_audit_log(
        session,
        session_id="s-1",
        user_text="gọi em qua 0912345678 nhé, cần máy lạnh",
        result=_turn_result(),
    )
    assert row is not None and row.id is not None

    stored = session.scalars(select(AuditLog)).one()
    assert stored.session_id == "s-1"
    assert stored.intent == "tu_van"
    assert stored.category == "may_lanh"
    assert stored.response_kind == "recommend"
    assert "0912345678" not in stored.user_message_masked  # PII masked before insert
    assert "***" in stored.user_message_masked
    assert stored.need_profile is not None
    assert stored.need_profile["slots"] == {"ngan_sach_max": 15_000_000}
    assert stored.total_candidates == 3
    assert stored.verdict_counts == {"match": 1, "mismatch": 1}
    assert stored.verifier_flags is not None and stored.verifier_flags[0]["action"] == "corrected"
    assert stored.source_panel is not None and stored.source_panel[0]["sku"] == "sku_a"
    assert stored.regenerated is True
    assert stored.timings_ms == {"s2": 400.0}


def test_write_failure_is_swallowed_and_rolled_back(session: Session) -> None:
    # Drop the table to force an insert failure — the writer must not raise.
    AuditLog.__table__.drop(session.get_bind())
    row = write_audit_log(session, session_id="s-2", user_text="hi", result=_turn_result())
    assert row is None
    # The session must remain usable after the swallowed failure.
    AuditLog.__table__.create(session.get_bind())
    assert write_audit_log(session, session_id="s-3", user_text="hi", result=_turn_result()) is not None