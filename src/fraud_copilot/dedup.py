"""Alert dedup/merge (LLD.md sec 2.1)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from .models import Alert, Case, DedupClassification
from .storage import Store

MERGE_WINDOW_MINUTES = 30


def compute_idempotency_key(alert: Alert) -> str:
    """Delimited hash -- never plain concatenation, so short-field values can't collide
    (e.g. customer_id='12'+transaction_id='3459' vs customer_id='123'+transaction_id='459')."""
    if alert.idempotency_key:
        return alert.idempotency_key
    raw = f"{alert.customer_id}|{alert.transaction_id}|{alert.alert_reason}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DedupResult:
    classification: DedupClassification
    idempotency_key: str
    existing_case: Optional[Case] = None


def classify(alert: Alert, store: Store) -> DedupResult:
    idempotency_key = compute_idempotency_key(alert)

    # Duplicate check spans open AND closed cases -- not time-limited to open ones.
    existing = store.find_case_by_idempotency_key(idempotency_key)
    if existing is not None:
        return DedupResult(DedupClassification.DUPLICATE, idempotency_key, existing)

    # Merge check is limited to OPEN cases for this customer, within the merge window.
    for case in store.open_cases_for_customer(alert.customer_id):
        if alert.alert_time - _last_alert_time(case) <= timedelta(minutes=MERGE_WINDOW_MINUTES):
            return DedupResult(DedupClassification.MERGED, idempotency_key, case)

    return DedupResult(DedupClassification.NEW_CASE, idempotency_key, None)


def _last_alert_time(case: Case):
    # In this local implementation the case's created_at stands in for "last alert time";
    # a production version would track per-alert timestamps on the case.
    return case.created_at
