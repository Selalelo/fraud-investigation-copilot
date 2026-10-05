"""In-memory case/snapshot store. Enforces write-once snapshots (LLD.md sec 4)."""
from __future__ import annotations

from typing import Dict, List, Optional

from .models import Case, CaseStatus, EvidenceSnapshot


class SnapshotAlreadyExistsError(Exception):
    pass


class Store:
    def __init__(self) -> None:
        self._cases: Dict[str, Case] = {}
        self._snapshots: Dict[str, EvidenceSnapshot] = {}
        self._idempotency_index: Dict[str, str] = {}  # idempotency_key -> case_id

    # -- cases ---------------------------------------------------------
    def save_case(self, case: Case) -> None:
        self._cases[case.case_id] = case

    def get_case(self, case_id: str) -> Optional[Case]:
        return self._cases.get(case_id)

    def open_cases_for_customer(self, customer_id: str) -> List[Case]:
        return [
            c
            for c in self._cases.values()
            if c.customer_id == customer_id and c.status == CaseStatus.OPEN
        ]

    def all_cases(self) -> List[Case]:
        return list(self._cases.values())

    # -- idempotency -----------------------------------------------------
    def find_case_by_idempotency_key(self, idempotency_key: str) -> Optional[Case]:
        case_id = self._idempotency_index.get(idempotency_key)
        return self._cases.get(case_id) if case_id else None

    def register_idempotency_key(self, idempotency_key: str, case_id: str) -> None:
        self._idempotency_index[idempotency_key] = case_id

    # -- snapshots --------------------------------------------------------
    def save_snapshot(self, snapshot: EvidenceSnapshot) -> None:
        if snapshot.snapshot_id in self._snapshots:
            raise SnapshotAlreadyExistsError(
                f"snapshot {snapshot.snapshot_id} already exists -- snapshots are write-once"
            )
        self._snapshots[snapshot.snapshot_id] = snapshot

    def get_snapshot(self, snapshot_id: str) -> Optional[EvidenceSnapshot]:
        return self._snapshots.get(snapshot_id)
