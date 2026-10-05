"""Indicator & counter-indicator engine (LLD.md sec 5). 12 rules, each with severity
(indicators only) and evidence ID(s). A rule whose dependent source isn't FOUND does not fire."""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Dict, List

from .models import (
    Alert,
    EvidenceSource,
    EvidenceSourceResult,
    EvidenceStatus,
    Indicator,
    IndicatorKind,
    Severity,
)

# Deterministic instruction-pattern check for IND-INJECTION-LIKE-TEXT (LLD.md sec 5.2 #12,
# sec 9). Runs directly against the alert's free text -- never passed raw to any LLM.
_INSTRUCTION_PATTERNS = re.compile(
    r"\b(ignore|disregard|forget)\b.{0,30}\b(prior|previous|above)\b.{0,30}\b(instructions?)\b"
    r"|\b(summari[sz]e|classify|mark|treat)\b.{0,20}\bas\b.{0,20}\b(low|no|zero)\b.{0,10}\brisk\b"
    r"|\bsystem\s*:\s*",
    re.IGNORECASE,
)


def _by_source(sources: List[EvidenceSourceResult]) -> Dict[EvidenceSource, EvidenceSourceResult]:
    return {r.source: r for r in sources}


def _found(result: EvidenceSourceResult) -> bool:
    return result is not None and result.status == EvidenceStatus.FOUND


def compute_indicators(alert: Alert, sources: List[EvidenceSourceResult]) -> List[Indicator]:
    by_source = _by_source(sources)
    out: List[Indicator] = []

    customer = by_source.get(EvidenceSource.CUSTOMER)
    transaction = by_source.get(EvidenceSource.TRANSACTION)
    beneficiary = by_source.get(EvidenceSource.BENEFICIARY)
    device = by_source.get(EvidenceSource.DEVICE)
    safps = by_source.get(EvidenceSource.SAFPS)

    # 1. IND-AMOUNT-HIGH (HIGH) -- TRANSACTION
    if _found(transaction):
        history = transaction.data.get("history_12m_amounts") or []
        if history and alert.amount / max(history) >= 3:
            out.append(Indicator(
                id="IND-AMOUNT-HIGH", kind=IndicatorKind.INDICATOR,
                statement=(
                    f"Amount is {alert.amount / max(history):.1f}x the 12-month maximum of "
                    f"R{max(history):,.0f} ({len(history)} transaction"
                    f"{'s' if len(history) != 1 else ''} analysed)"
                ),
                evidence_ids=(transaction.evidence_id,), severity=Severity.HIGH,
            ))

    # 2. IND-BENEFICIARY-NEW (MEDIUM) -- BENEFICIARY
    if _found(beneficiary):
        date_added = beneficiary.data.get("date_added")
        if date_added and alert.alert_time - date_added <= timedelta(minutes=60):
            minutes = int((alert.alert_time - date_added).total_seconds() // 60)
            out.append(Indicator(
                id="IND-BENEFICIARY-NEW", kind=IndicatorKind.INDICATOR,
                statement=f"Beneficiary added {minutes} min before this transfer",
                evidence_ids=(beneficiary.evidence_id,), severity=Severity.MEDIUM,
            ))

    # 3. IND-BENEFICIARY-LINKED (HIGH) -- BENEFICIARY (known-bad destination, NOT the mule signal)
    if _found(beneficiary):
        prior = beneficiary.data.get("prior_case_count", 0)
        if prior >= 1:
            out.append(Indicator(
                id="IND-BENEFICIARY-LINKED", kind=IndicatorKind.INDICATOR,
                statement=f"Beneficiary appears in {prior} prior case(s)",
                evidence_ids=(beneficiary.evidence_id,), severity=Severity.HIGH,
            ))

    # 4. IND-BENEFICIARY-EXTERNAL (LOW) -- BENEFICIARY
    if _found(beneficiary) and beneficiary.data.get("external"):
        out.append(Indicator(
            id="IND-BENEFICIARY-EXTERNAL", kind=IndicatorKind.INDICATOR,
            statement="Beneficiary account is external to this bank",
            evidence_ids=(beneficiary.evidence_id,), severity=Severity.LOW,
        ))

    # 5. IND-DEVICE-UNUSUAL (MEDIUM) -- DEVICE
    if _found(device) and not device.data.get("is_usual_device", True):
        out.append(Indicator(
            id="IND-DEVICE-UNUSUAL", kind=IndicatorKind.INDICATOR,
            statement="Login device is not the customer's usual device",
            evidence_ids=(device.evidence_id,), severity=Severity.MEDIUM,
        ))

    # 6. IND-RECENT-SIM-SWAP (HIGH) -- DEVICE
    if _found(device):
        sim_swap_days = device.data.get("last_sim_swap_days")
        if sim_swap_days is not None and sim_swap_days <= 7:
            out.append(Indicator(
                id="IND-RECENT-SIM-SWAP", kind=IndicatorKind.INDICATOR,
                statement=f"SIM swap {sim_swap_days} days ago",
                evidence_ids=(device.evidence_id,), severity=Severity.HIGH,
            ))

    # 7. CI-DEVICE-USUAL -- DEVICE
    if _found(device) and device.data.get("is_usual_device") and device.data.get("is_usual_location"):
        out.append(Indicator(
            id="CI-DEVICE-USUAL", kind=IndicatorKind.COUNTER_INDICATOR,
            statement="Login from usual device and usual location",
            evidence_ids=(device.evidence_id,), severity=None,
        ))

    # 8. CI-NO-CREDENTIAL-CHANGE -- DEVICE
    if _found(device):
        no_sim_swap = device.data.get("last_sim_swap_days") is None
        no_pw_reset = device.data.get("last_password_reset_days") is None
        if no_sim_swap and no_pw_reset:
            out.append(Indicator(
                id="CI-NO-CREDENTIAL-CHANGE", kind=IndicatorKind.COUNTER_INDICATOR,
                statement="No recent password reset or SIM swap",
                evidence_ids=(device.evidence_id,), severity=None,
            ))

    # 9. CI-CUSTOMER-TENURE -- CUSTOMER
    if _found(customer):
        if customer.data.get("tenure_years", 0) >= 3 and customer.data.get("prior_case_count", 0) == 0:
            out.append(Indicator(
                id="CI-CUSTOMER-TENURE", kind=IndicatorKind.COUNTER_INDICATOR,
                statement=f"Customer tenure {customer.data['tenure_years']} years, no prior cases",
                evidence_ids=(customer.evidence_id,), severity=None,
            ))

    # 10. IND-SAFPS-GRID-HIT (HIGH) -- SAFPS (mock)
    if _found(safps) and safps.data.get("grid_match"):
        category = safps.data.get("alert_category") or "unspecified"
        out.append(Indicator(
            id="IND-SAFPS-GRID-HIT", kind=IndicatorKind.INDICATOR,
            statement=f"Beneficiary matches an active SAFPS grid alert ({category})",
            evidence_ids=(safps.evidence_id,), severity=Severity.HIGH,
        ))

    # 11. IND-RAPID-PASSTHROUGH (HIGH) -- TRANSACTION (the real MULE signal)
    if _found(transaction):
        recent_inbound = transaction.data.get("recent_large_inbound")
        days_before = transaction.data.get("recent_large_inbound_days_before")
        if recent_inbound and days_before is not None and days_before <= 3:
            out.append(Indicator(
                id="IND-RAPID-PASSTHROUGH", kind=IndicatorKind.INDICATOR,
                statement=f"Large inbound deposit {days_before} day(s) before this outgoing transfer",
                evidence_ids=(transaction.evidence_id,), severity=Severity.HIGH,
            ))

    # 12. IND-INJECTION-LIKE-TEXT (LOW, informational) -- computed directly from the alert
    injection_source_text = f"{alert.payment_reference} {alert.beneficiary_name}"
    if _INSTRUCTION_PATTERNS.search(injection_source_text):
        # No fetched evidence source backs this -- it's computed from the alert itself, but is
        # cited against the TRANSACTION evidence_id (always 'E2', assigned regardless of FOUND
        # status -- see evidence_sources.gather_all) since the citation regex requires a numeric
        # [E\d+] id and the transaction evidence result object always exists for this case.
        out.append(Indicator(
            id="IND-INJECTION-LIKE-TEXT", kind=IndicatorKind.INDICATOR,
            statement="Payment reference or beneficiary name contains text resembling an instruction",
            evidence_ids=(transaction.evidence_id,), severity=Severity.LOW,
        ))

    return out


def split_indicators(indicators: List[Indicator]):
    real = [i for i in indicators if i.kind == IndicatorKind.INDICATOR]
    counters = [i for i in indicators if i.kind == IndicatorKind.COUNTER_INDICATOR]
    return real, counters
