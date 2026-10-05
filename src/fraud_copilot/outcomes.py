"""Outcomes table and feedback metrics (LLD.md sec 12, design sec 3.13/7).

Write access restricted to an authorised_reviewer role, to prevent label poisoning of the
feedback loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

OUTCOMES = {
    "CONFIRMED_FRAUD", "CONFIRMED_LEGITIMATE", "CUSTOMER_DISPUTE",
    "RECOVERED", "LAW_ENFORCEMENT_REQUEST", "UNKNOWN",
}


class UnauthorisedReviewerError(Exception):
    pass


@dataclass(frozen=True)
class Outcome:
    case_id: str
    outcome: str
    recorded_by: str
    recorded_at: datetime
    notes: str = ""


class OutcomeStore:
    def __init__(self, authorised_reviewers: set) -> None:
        self._authorised_reviewers = set(authorised_reviewers)
        self._outcomes: List[Outcome] = []

    def record_outcome(self, case_id: str, outcome: str, recorded_by: str, notes: str = "") -> Outcome:
        if recorded_by not in self._authorised_reviewers:
            raise UnauthorisedReviewerError(f"{recorded_by} is not an authorised reviewer")
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}")
        record = Outcome(
            case_id=case_id, outcome=outcome, recorded_by=recorded_by,
            recorded_at=datetime.now(timezone.utc), notes=notes,
        )
        self._outcomes.append(record)
        return record

    def all_outcomes(self) -> List[Outcome]:
        return list(self._outcomes)


def decision_outcome_agreement_rate(decisions: dict, outcomes: List[Outcome]) -> float:
    """Design sec 7 'decision quality': agreement between investigator decisions and confirmed
    outcomes. decisions: {case_id: decision_str}. Simple mapping: BLOCK/ESCALATE agree with
    CONFIRMED_FRAUD; RELEASE agrees with CONFIRMED_LEGITIMATE. Returns None if there's nothing
    to compare."""
    agreeing_pairs = {
        ("BLOCK", "CONFIRMED_FRAUD"), ("ESCALATE", "CONFIRMED_FRAUD"),
        ("RELEASE", "CONFIRMED_LEGITIMATE"),
    }
    compared = 0
    agreed = 0
    for outcome in outcomes:
        decision = decisions.get(outcome.case_id)
        if decision is None:
            continue
        compared += 1
        if (decision, outcome.outcome) in agreeing_pairs:
            agreed += 1
    if compared == 0:
        return None
    return agreed / compared
