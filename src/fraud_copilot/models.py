"""Dataclasses for the Fraud Investigation Copilot core pipeline (LLD.md sec 2-6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class ImmediateAction(str, Enum):
    HOLD = "HOLD"
    STEP_UP = "STEP_UP"
    DELAY = "DELAY"
    ALLOW = "ALLOW"


class PaymentRail(str, Enum):
    RTC = "RTC"
    PAYSHAP = "PAYSHAP"
    EFT = "EFT"
    INTERNAL = "INTERNAL"


class EvidenceSource(str, Enum):
    CUSTOMER = "CUSTOMER"
    TRANSACTION = "TRANSACTION"
    BENEFICIARY = "BENEFICIARY"
    DEVICE = "DEVICE"
    KYC = "KYC"
    SAFPS = "SAFPS"


class EvidenceStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    FAILED = "FAILED"


class IndicatorKind(str, Enum):
    INDICATOR = "INDICATOR"
    COUNTER_INDICATOR = "COUNTER_INDICATOR"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class LikelyScenario(str, Enum):
    MULE = "MULE"
    ACCOUNT_TAKEOVER = "ACCOUNT_TAKEOVER"
    APP_SCAM = "APP_SCAM"
    FIRST_PARTY = "FIRST_PARTY"
    UNCLASSIFIED = "UNCLASSIFIED"


class DedupClassification(str, Enum):
    NEW_CASE = "NEW_CASE"
    DUPLICATE = "DUPLICATE"
    MERGED = "MERGED"


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    DECIDED = "DECIDED"


class NarrativeStatus(str, Enum):
    VALIDATED = "VALIDATED"
    UNAVAILABLE = "UNAVAILABLE"


class ValidationOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Alert:
    """LLD.md sec 2."""

    alert_id: str
    customer_id: str
    transaction_id: str
    amount: float
    beneficiary_id: str
    beneficiary_bank: str
    alert_reason: str
    immediate_action: ImmediateAction
    alert_time: datetime
    received_time: datetime
    beneficiary_name: str = ""
    payment_rail: PaymentRail = PaymentRail.EFT
    proxy_id: Optional[str] = None
    payment_reference: str = ""
    idempotency_key: Optional[str] = None
    data_source: str = "SYNTHETIC"  # "SYNTHETIC" (hand-crafted fixture) or "AMLSIM_REAL"
    # (built from a genuine IBM AMLSim simulator run -- see amlsim_import.py). Surfaced in the
    # UI/render so a real-data case is never visually indistinguishable from the demo fixtures.


@dataclass(frozen=True)
class EvidenceSourceResult:
    """LLD.md sec 3."""

    source: EvidenceSource
    status: EvidenceStatus
    evidence_id: str
    fetched_at: datetime
    timeout_ms: int
    elapsed_ms: int
    data: Optional[dict] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class EvidenceSnapshot:
    """LLD.md sec 4. Write-once once constructed; see storage.py for the enforcement."""

    snapshot_id: str
    case_id: str
    created_at: datetime
    sources: tuple  # tuple[EvidenceSourceResult, ...] -- tuple for immutability
    content_hash: str
    storage_uri: str


@dataclass(frozen=True)
class Indicator:
    """LLD.md sec 5.1."""

    id: str
    kind: IndicatorKind
    statement: str
    evidence_ids: tuple
    severity: Optional[Severity] = None  # indicators only


@dataclass(frozen=True)
class ValidationResult:
    """LLD.md sec 10.2."""

    case_id: str
    result: ValidationOutcome
    failed_rule: Optional[str]
    narrative_checked: str
    validated_at: datetime


@dataclass
class Case:
    """LLD.md sec 6. Mutable -- accumulates snapshots/indicators as the pipeline runs."""

    case_id: str
    alert_ids: list
    customer_id: str
    beneficiary_ids: list
    amount: float
    immediate_action: ImmediateAction
    snapshot_ids: list
    latest_snapshot_id: Optional[str]
    priority: Optional[Priority]
    sla_deadline: Optional[datetime]
    likely_scenario: LikelyScenario
    scenario_evidence: list
    indicators: list
    counter_indicators: list
    evidence_incomplete_warnings: list
    linked_entities: list
    narrative: Optional[str]
    narrative_status: Optional[NarrativeStatus]
    status: CaseStatus
    created_at: datetime
    data_source: str = "SYNTHETIC"  # copied from Alert.data_source at case creation
    payment_rail: PaymentRail = PaymentRail.EFT  # copied from Alert.payment_rail at case creation
    payment_reference: str = ""  # copied from Alert.payment_reference at case creation
    proxy_id: Optional[str] = None  # copied from Alert.proxy_id at case creation


SLA_MINUTES = {
    Priority.HIGH: 60,
    Priority.MEDIUM: 240,
    Priority.LOW: 24 * 60,
}


def sla_deadline_for(priority: Priority, created_at: datetime) -> datetime:
    return created_at + timedelta(minutes=SLA_MINUTES[priority])
