"""
LLM-optional path: ensure ``LLM_MODEL=none`` skips network calls and does not error.

Complements ``tests/test_orchestrator.py`` (which also patches ``LLM_MODEL`` to
``"none"``) with direct checks on :mod:`pipeline.llm_classifier` and
classifier runtime helpers.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from api.models import UserSecrets
from api.services import classifier_runtime as cr
from pipeline import config as pc
import pipeline.llm_classifier as llm_classifier_mod
from pipeline.config import LLM_FALLBACK_CHAIN
from pipeline.llm_classifier import classify_llm
from pipeline.models import CanonicalTransaction, Channel, Direction, TxnType


def _minimal_work_item() -> CanonicalTransaction:
    """One row with missing counterparty so :func:`_build_work_items` would find work (if not none)."""
    return CanonicalTransaction(
        txn_id="T_99000001",
        txn_date=date(2024, 1, 10),
        account_id="A",
        source_statement="hdfc_savings",
        direction=Direction.OUTFLOW,
        amount=Decimal("1.0"),
        currency="INR",
        txn_type=TxnType.UPI_EXPENSE,
        channel=Channel.UPI,
        counterparty=None,
        counterparty_category=None,
        raw_description="UPI/SOME UNKNOWN MERCHANT/xyz@okaxis",
    )


def test_auto_fallback_chain_only_includes_providers_with_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LLM_MODEL=auto`` must not schedule Gemini/Claude when those keys are absent."""
    monkeypatch.setattr(llm_classifier_mod._cfg, "OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setattr(llm_classifier_mod._cfg, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(llm_classifier_mod._cfg, "GOOGLE_API_KEY", "")
    assert llm_classifier_mod._auto_fallback_chain() == ["gpt-5-mini"]

    monkeypatch.setattr(llm_classifier_mod._cfg, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm_classifier_mod._cfg, "ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(llm_classifier_mod._cfg, "GOOGLE_API_KEY", "")
    assert llm_classifier_mod._auto_fallback_chain() == ["claude-haiku-4-5"]

    monkeypatch.setattr(llm_classifier_mod._cfg, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm_classifier_mod._cfg, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(llm_classifier_mod._cfg, "GOOGLE_API_KEY", "AIza-test")
    assert llm_classifier_mod._auto_fallback_chain() == [
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
    ]

    monkeypatch.setattr(llm_classifier_mod._cfg, "OPENAI_API_KEY", "sk-o")
    monkeypatch.setattr(llm_classifier_mod._cfg, "ANTHROPIC_API_KEY", "sk-a")
    monkeypatch.setattr(llm_classifier_mod._cfg, "GOOGLE_API_KEY", "AIza")
    assert llm_classifier_mod._auto_fallback_chain() == list(LLM_FALLBACK_CHAIN)


def test_classify_llm_with_model_none_is_noop() -> None:
    """When ``LLM_MODEL`` is ``none``, the classifier returns the same list without side effects."""
    work = _minimal_work_item()
    before = [work]
    old = pc.LLM_MODEL
    try:
        pc.LLM_MODEL = "none"
        out = classify_llm(before)
    finally:
        pc.LLM_MODEL = old
    assert out is before
    # Still incomplete — rules/LLM did not fill; we only assert no crash
    assert out[0].counterparty is None


@pytest.fixture(name="engine")
def _engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose()


def test_effective_onboarding_threshold_low_when_llm_disabled(
    engine: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror onboarding UX: with ``LLM_MODEL=none`` we use the *low* unknown cap."""
    import pipeline.config as pipeline_cfg

    for k in (
        "OPENAI_API_KEY",
        "OPENAI_API_KEY_FOR_CLASSIFIER",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEY_FOR_CLASSIFIER",
        "GOOGLE_API_KEY",
        "GOOGLE_API_KEY_FOR_CLASSIFIER",
    ):
        monkeypatch.setenv(k, "")

    monkeypatch.setenv("ONBOARDING_UNKNOWN_THRESHOLD_LOW", "7")

    old = pipeline_cfg.LLM_MODEL
    try:
        pipeline_cfg.LLM_MODEL = "none"
        with Session(engine) as session:  # type: ignore[call-arg]
            assert cr.effective_onboarding_unknown_threshold(session, "u") == 7
    finally:
        pipeline_cfg.LLM_MODEL = old


def test_user_stored_openai_key_persisted_in_user_secrets(engine: object) -> None:
    """Storing a provider key in ``UserSecrets`` is readable back as JSON (round-trip)."""
    payload = '{"OPENAI_API_KEY_FOR_CLASSIFIER": "sk-test-abc"}'
    with Session(engine) as session:  # type: ignore[call-arg]
        session.add(UserSecrets(user_id="key_user", secrets_json=payload))
        session.commit()
    with Session(engine) as session:  # type: ignore[call-arg]
        row = session.exec(select(UserSecrets).where(UserSecrets.user_id == "key_user")).first()
        assert row is not None
        assert "sk-test-abc" in (row.secrets_json or "")


def test_user_stored_classifier_presence_ignores_process_env(
    engine: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``user_stored_classifier_api_key_presence`` must not treat ``OPENAI_*`` in env as stored keys."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env-not-usersecrets")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    with Session(engine) as session:  # type: ignore[call-arg]
        ho, ha, hg = cr.user_stored_classifier_api_key_presence(session, "no_row_yet")
        assert (ho, ha, hg) == (False, False, False)


def test_onboarding_should_resume_after_classify_zero_threshold() -> None:
    """Default resume policy: only continue backfill when the review queue is empty."""
    assert cr.onboarding_should_resume_after_classify(0, 0) is True
    assert cr.onboarding_should_resume_after_classify(1, 0) is False
    assert cr.onboarding_should_resume_after_classify(0, 5) is True
    assert cr.onboarding_should_resume_after_classify(4, 5) is True
    assert cr.onboarding_should_resume_after_classify(5, 5) is False
