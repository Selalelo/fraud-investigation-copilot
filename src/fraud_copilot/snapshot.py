"""Evidence snapshot construction (LLD.md sec 4). Write-once, hashed."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from enum import Enum

from .models import EvidenceSnapshot, EvidenceSourceResult


def _canonical(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    return obj


def _source_to_dict(r: EvidenceSourceResult) -> dict:
    return {
        "source": r.source, "status": r.status, "evidence_id": r.evidence_id,
        "fetched_at": r.fetched_at, "timeout_ms": r.timeout_ms, "elapsed_ms": r.elapsed_ms,
        "data": r.data, "error": r.error,
    }


def content_hash(sources: list) -> str:
    canonical = _canonical([_source_to_dict(r) for r in sources])
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_snapshot(case_id: str, sources: list) -> EvidenceSnapshot:
    snapshot_id = str(uuid.uuid4())
    h = content_hash(sources)
    return EvidenceSnapshot(
        snapshot_id=snapshot_id,
        case_id=case_id,
        created_at=datetime.utcnow(),
        sources=tuple(sources),
        content_hash=h,
        storage_uri=f"local://snapshots/{snapshot_id}.json",
    )
