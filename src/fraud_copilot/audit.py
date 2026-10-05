"""Append-only audit log (LLD.md sec 11). No update/delete method exists -- only append."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from .models import Case, ValidationResult
from .storage import Store

REASON_CODES = {
    "GENUINE_FRAUD_CONFIRMED", "CUSTOMER_CONFIRMED_LEGITIMATE",
    "INSUFFICIENT_EVIDENCE", "AWAITING_CUSTOMER_RESPONSE", "ESCALATED_TO_SPECIALIST",
    "SUSPECTED_MULE_ACCOUNT", "STANDARD_MONITORING",
}


class InvalidDecisionError(Exception):
    pass


@dataclass(frozen=True)
class EvidenceView:
    case_id: str
    evidence_id: str
    investigator_id: str
    viewed_at: datetime


@dataclass(frozen=True)
class AuditRecord:
    case_id: str
    snapshot_hash: str
    model_version: str
    prompt_version: str
    narrative: Optional[str]
    validation_result: Optional[ValidationResult]
    evidence_views: List[EvidenceView]
    decision: str
    reason_code: str
    rationale: str
    decided_by: str
    decided_at: datetime


class AuditLog:
    """Append-only: entries are added via record_decision, never edited or removed."""

    def __init__(self) -> None:
        self._entries: List[AuditRecord] = []
        self._views: List[EvidenceView] = []

    def record_evidence_view(self, case_id: str, evidence_id: str, investigator_id: str) -> None:
        self._views.append(EvidenceView(
            case_id=case_id, evidence_id=evidence_id, investigator_id=investigator_id,
            viewed_at=datetime.now(timezone.utc),
        ))

    def record_decision(
        self,
        case: Case,
        store: Store,
        decision: str,
        reason_code: str,
        rationale: str,
        decided_by: str,
        validation_result: Optional[ValidationResult] = None,
        model_version: str = "mock-llm-v1",
        prompt_version: str = "v1",
    ) -> AuditRecord:
        if not reason_code or reason_code not in REASON_CODES:
            raise InvalidDecisionError(f"reason_code is mandatory and must be one of {REASON_CODES}")
        if not rationale or not rationale.strip():
            raise InvalidDecisionError("rationale is mandatory free text")

        snapshot = store.get_snapshot(case.latest_snapshot_id) if case.latest_snapshot_id else None
        snapshot_hash = snapshot.content_hash if snapshot else ""

        record = AuditRecord(
            case_id=case.case_id,
            snapshot_hash=snapshot_hash,
            model_version=model_version,
            prompt_version=prompt_version,
            narrative=case.narrative,
            validation_result=validation_result,
            evidence_views=[v for v in self._views if v.case_id == case.case_id],
            decision=decision,
            reason_code=reason_code,
            rationale=rationale,
            decided_by=decided_by,
            decided_at=datetime.now(timezone.utc),
        )
        self._entries.append(record)
        return record

    def entries_for_case(self, case_id: str) -> List[AuditRecord]:
        return [e for e in self._entries if e.case_id == case_id]

    def all_entries(self) -> List[AuditRecord]:
        return list(self._entries)
