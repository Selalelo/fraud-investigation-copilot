"""Six mock evidence sources (LLD.md sec 3.1). SAFPS is explicitly a mock -- no verified
real-world programmatic access."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from .models import Alert, EvidenceSource, EvidenceSourceResult, EvidenceStatus

TIMEOUT_MS = 2000


@dataclass
class CustomerRecord:
    tenure_years: float
    kyc_tier: str
    monthly_spend_min: float
    monthly_spend_max: float
    prior_case_count: int


@dataclass
class TransactionRecord:
    history_12m_amounts: list
    recent_large_inbound: bool = False
    recent_large_inbound_amount: Optional[float] = None
    recent_large_inbound_days_before: Optional[int] = None


@dataclass
class BeneficiaryRecord:
    account_age_days: int
    external: bool
    date_added: datetime
    prior_case_count: int


@dataclass
class DeviceRecord:
    device_fingerprint: str
    is_usual_device: bool
    is_usual_location: bool
    last_sim_swap_days: Optional[int] = None
    last_password_reset_days: Optional[int] = None
    phone_number: Optional[str] = None
    ip_address: Optional[str] = None


@dataclass
class KYCRecord:
    verification_status: str
    last_updated: datetime


@dataclass
class SAFPSRecord:
    grid_match: bool
    alert_category: Optional[str] = None
    date_added_to_grid: Optional[datetime] = None


# Sentinel record values that simulate a source failure/timeout in synthetic data.
FAIL_SENTINEL = "__FAIL__"
NOT_AVAILABLE_SENTINEL = "__NOT_AVAILABLE__"


@dataclass
class SyntheticWorld:
    """Keyed synthetic dataset the mock sources read from. Missing keys -> NOT_FOUND."""

    customers: Dict[str, CustomerRecord] = field(default_factory=dict)
    transactions: Dict[str, TransactionRecord] = field(default_factory=dict)
    beneficiaries: Dict[str, BeneficiaryRecord] = field(default_factory=dict)
    devices: Dict[str, DeviceRecord] = field(default_factory=dict)
    kyc: Dict[str, KYCRecord] = field(default_factory=dict)
    safps: Dict[str, SAFPSRecord] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _result(
    source: EvidenceSource,
    evidence_id: str,
    key: str,
    table: Dict[str, object],
    to_data: Callable[[object], dict],
) -> EvidenceSourceResult:
    fetched_at = _now()
    if key == FAIL_SENTINEL:
        return EvidenceSourceResult(
            source=source, status=EvidenceStatus.FAILED, evidence_id=evidence_id,
            fetched_at=fetched_at, timeout_ms=TIMEOUT_MS, elapsed_ms=TIMEOUT_MS,
            data=None, error="simulated timeout/failure",
        )
    if key == NOT_AVAILABLE_SENTINEL:
        return EvidenceSourceResult(
            source=source, status=EvidenceStatus.NOT_AVAILABLE, evidence_id=evidence_id,
            fetched_at=fetched_at, timeout_ms=TIMEOUT_MS, elapsed_ms=5, data=None,
        )
    record = table.get(key)
    if record is None:
        return EvidenceSourceResult(
            source=source, status=EvidenceStatus.NOT_FOUND, evidence_id=evidence_id,
            fetched_at=fetched_at, timeout_ms=TIMEOUT_MS, elapsed_ms=5, data=None,
        )
    return EvidenceSourceResult(
        source=source, status=EvidenceStatus.FOUND, evidence_id=evidence_id,
        fetched_at=fetched_at, timeout_ms=TIMEOUT_MS, elapsed_ms=5, data=to_data(record),
    )


def fetch_customer(alert: Alert, world: SyntheticWorld, evidence_id: str) -> EvidenceSourceResult:
    return _result(
        EvidenceSource.CUSTOMER, evidence_id, alert.customer_id, world.customers,
        lambda r: {
            "tenure_years": r.tenure_years, "kyc_tier": r.kyc_tier,
            "monthly_spend_min": r.monthly_spend_min, "monthly_spend_max": r.monthly_spend_max,
            "prior_case_count": r.prior_case_count,
        },
    )


def fetch_transaction(alert: Alert, world: SyntheticWorld, evidence_id: str) -> EvidenceSourceResult:
    return _result(
        EvidenceSource.TRANSACTION, evidence_id, alert.customer_id, world.transactions,
        lambda r: {
            "history_12m_amounts": r.history_12m_amounts,
            "recent_large_inbound": r.recent_large_inbound,
            "recent_large_inbound_amount": r.recent_large_inbound_amount,
            "recent_large_inbound_days_before": r.recent_large_inbound_days_before,
        },
    )


def fetch_beneficiary(alert: Alert, world: SyntheticWorld, evidence_id: str) -> EvidenceSourceResult:
    return _result(
        EvidenceSource.BENEFICIARY, evidence_id, alert.beneficiary_id, world.beneficiaries,
        lambda r: {
            "account_age_days": r.account_age_days, "external": r.external,
            "date_added": r.date_added, "prior_case_count": r.prior_case_count,
        },
    )


def fetch_device(alert: Alert, world: SyntheticWorld, evidence_id: str) -> EvidenceSourceResult:
    return _result(
        EvidenceSource.DEVICE, evidence_id, alert.customer_id, world.devices,
        lambda r: {
            "device_fingerprint": r.device_fingerprint, "is_usual_device": r.is_usual_device,
            "is_usual_location": r.is_usual_location, "last_sim_swap_days": r.last_sim_swap_days,
            "last_password_reset_days": r.last_password_reset_days,
            "phone_number": r.phone_number, "ip_address": r.ip_address,
        },
    )


def fetch_kyc(alert: Alert, world: SyntheticWorld, evidence_id: str) -> EvidenceSourceResult:
    return _result(
        EvidenceSource.KYC, evidence_id, alert.customer_id, world.kyc,
        lambda r: {"verification_status": r.verification_status, "last_updated": r.last_updated},
    )


def fetch_safps(alert: Alert, world: SyntheticWorld, evidence_id: str) -> EvidenceSourceResult:
    """Mock source -- SAFPS real-world programmatic access is unverified (LLD.md sec 3.1)."""
    key = alert.proxy_id or alert.beneficiary_id
    return _result(
        EvidenceSource.SAFPS, evidence_id, key, world.safps,
        lambda r: {
            "grid_match": r.grid_match, "alert_category": r.alert_category,
            "date_added_to_grid": r.date_added_to_grid,
        },
    )


ALL_SOURCE_FETCHERS = {
    EvidenceSource.CUSTOMER: fetch_customer,
    EvidenceSource.TRANSACTION: fetch_transaction,
    EvidenceSource.BENEFICIARY: fetch_beneficiary,
    EvidenceSource.DEVICE: fetch_device,
    EvidenceSource.KYC: fetch_kyc,
    EvidenceSource.SAFPS: fetch_safps,
}


def gather_all(alert: Alert, world: SyntheticWorld) -> list:
    """Runs all six sources independently -- one FAILED/NOT_AVAILABLE source never blocks another."""
    results = []
    for idx, (source, fetcher) in enumerate(ALL_SOURCE_FETCHERS.items(), start=1):
        results.append(fetcher(alert, world, evidence_id=f"E{idx}"))
    return results
