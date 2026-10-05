"""Scenario classifier (LLD.md sec 8, post design-review fix).

Deterministic, rule-based. Output is always 'consistent with' a scenario, never an assertion --
scenario_evidence names exactly which rule(s) produced the label. MULE is evaluated first, driven
by IND-RAPID-PASSTHROUGH (the customer's own account as pass-through), not by
IND-BENEFICIARY-LINKED (a suspect destination account, a different fact).
"""
from __future__ import annotations

from typing import List, Tuple

from .models import Indicator, LikelyScenario


def _ids(indicators: List[Indicator]) -> set:
    return {i.id for i in indicators}


def classify_scenario(
    indicators: List[Indicator], counter_indicators: List[Indicator]
) -> Tuple[LikelyScenario, List[str]]:
    ind_ids = _ids(indicators)
    ci_ids = _ids(counter_indicators)

    if "IND-RAPID-PASSTHROUGH" in ind_ids:
        return LikelyScenario.MULE, ["IND-RAPID-PASSTHROUGH"]

    if ("IND-DEVICE-UNUSUAL" in ind_ids or "IND-RECENT-SIM-SWAP" in ind_ids) and "CI-DEVICE-USUAL" not in ci_ids:
        evidence = [r for r in ("IND-DEVICE-UNUSUAL", "IND-RECENT-SIM-SWAP") if r in ind_ids]
        return LikelyScenario.ACCOUNT_TAKEOVER, evidence

    if (
        "CI-DEVICE-USUAL" in ci_ids
        and "CI-NO-CREDENTIAL-CHANGE" in ci_ids
        and "IND-BENEFICIARY-NEW" in ind_ids
        and "IND-AMOUNT-HIGH" in ind_ids
    ):
        return LikelyScenario.APP_SCAM, ["IND-BENEFICIARY-NEW", "IND-AMOUNT-HIGH"]

    device_or_beneficiary_indicators = ind_ids & {
        "IND-DEVICE-UNUSUAL", "IND-RECENT-SIM-SWAP",
        "IND-BENEFICIARY-NEW", "IND-BENEFICIARY-LINKED", "IND-BENEFICIARY-EXTERNAL",
    }
    if (
        "CI-CUSTOMER-TENURE" in ci_ids
        and not device_or_beneficiary_indicators
        and "IND-AMOUNT-HIGH" in ind_ids
    ):
        return LikelyScenario.FIRST_PARTY, ["IND-AMOUNT-HIGH"]

    return LikelyScenario.UNCLASSIFIED, []
