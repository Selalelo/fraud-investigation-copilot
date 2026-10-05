"""A DynamoDB/S3-backed Store -- a drop-in replacement for storage.Store's public interface, so
pipeline.process_alert() runs unmodified against either. Backed by the resources actually
deployed in infra/ (Stage B): the cases table, and the evidence-snapshots S3 bucket (matching
the design's real intent -- snapshots belong in S3 Object Lock storage, not a KV table).

Idempotency lookups use a marker-item pattern in the same cases table: an item with
case_id = "IDEMP#<idempotency_key>" holding {"real_case_id": <case_id>}, avoiding a second table
for a POC. Snapshots are stored as JSON objects at snapshots/<snapshot_id>.json in the evidence
bucket; write-once is enforced with a HeadObject existence check before PutObject (S3 Object
Lock governs the objects themselves once written -- see infra/s3.tf).
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError

from .models import (
    Case,
    CaseStatus,
    EvidenceSnapshot,
    EvidenceSource,
    EvidenceSourceResult,
    EvidenceStatus,
    Indicator,
    IndicatorKind,
    ImmediateAction,
    LikelyScenario,
    NarrativeStatus,
    PaymentRail,
    Priority,
    Severity,
)
from .storage import SnapshotAlreadyExistsError


def _to_json_safe(value):
    if is_dataclass(value):
        return {k: _to_json_safe(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(v) for v in value]
    return value


def _floats_to_decimal(value):
    """DynamoDB's Python SDK rejects native float -- convert recursively before put_item."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _floats_to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_floats_to_decimal(v) for v in value]
    return value


def _decimals_to_float(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _decimals_to_float(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decimals_to_float(v) for v in value]
    return value


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _indicator_from_dict(d: dict) -> Indicator:
    return Indicator(
        id=d["id"],
        kind=IndicatorKind(d["kind"]),
        statement=d["statement"],
        evidence_ids=tuple(d["evidence_ids"]),
        severity=Severity(d["severity"]) if d.get("severity") else None,
    )


def _case_to_item(case: Case) -> dict:
    item = {
        "case_id": case.case_id,
        "alert_ids": case.alert_ids,
        "customer_id": case.customer_id,
        "beneficiary_ids": case.beneficiary_ids,
        "amount": case.amount,
        "immediate_action": case.immediate_action.value,
        "snapshot_ids": case.snapshot_ids,
        "latest_snapshot_id": case.latest_snapshot_id,
        "priority": case.priority.value if case.priority else None,
        "sla_deadline": case.sla_deadline.isoformat() if case.sla_deadline else None,
        "likely_scenario": case.likely_scenario.value,
        "scenario_evidence": case.scenario_evidence,
        "indicators": [_to_json_safe(i) for i in case.indicators],
        "counter_indicators": [_to_json_safe(i) for i in case.counter_indicators],
        "evidence_incomplete_warnings": case.evidence_incomplete_warnings,
        "linked_entities": [_to_json_safe(l) for l in case.linked_entities],
        "narrative": case.narrative,
        "narrative_status": case.narrative_status.value if case.narrative_status else None,
        "status": case.status.value,
        "created_at": case.created_at.isoformat(),
        "data_source": case.data_source,
        "payment_rail": case.payment_rail.value,
        "payment_reference": case.payment_reference,
        "proxy_id": case.proxy_id,
    }
    return _floats_to_decimal(item)


def _item_to_case(item: dict) -> Case:
    item = _decimals_to_float(item)
    return Case(
        case_id=item["case_id"],
        alert_ids=list(item["alert_ids"]),
        customer_id=item["customer_id"],
        beneficiary_ids=list(item["beneficiary_ids"]),
        amount=item["amount"],
        immediate_action=ImmediateAction(item["immediate_action"]),
        snapshot_ids=list(item["snapshot_ids"]),
        latest_snapshot_id=item.get("latest_snapshot_id"),
        priority=Priority(item["priority"]) if item.get("priority") else None,
        sla_deadline=_parse_dt(item.get("sla_deadline")),
        likely_scenario=LikelyScenario(item["likely_scenario"]),
        scenario_evidence=list(item.get("scenario_evidence", [])),
        indicators=[_indicator_from_dict(d) for d in item.get("indicators", [])],
        counter_indicators=[_indicator_from_dict(d) for d in item.get("counter_indicators", [])],
        evidence_incomplete_warnings=list(item.get("evidence_incomplete_warnings", [])),
        linked_entities=[],  # graph links are re-resolved on read, not stored verbatim in this POC
        narrative=item.get("narrative"),
        narrative_status=NarrativeStatus(item["narrative_status"]) if item.get("narrative_status") else None,
        status=CaseStatus(item["status"]),
        created_at=_parse_dt(item["created_at"]),
        data_source=item.get("data_source", "SYNTHETIC"),
        payment_rail=PaymentRail(item["payment_rail"]) if item.get("payment_rail") else PaymentRail.EFT,
        payment_reference=item.get("payment_reference", ""),
        proxy_id=item.get("proxy_id"),
    )


class DynamoStore:
    def __init__(self, cases_table_name: str, evidence_bucket_name: str, region: str = "us-east-1"):
        self._table = boto3.resource("dynamodb", region_name=region).Table(cases_table_name)
        self._s3 = boto3.client("s3", region_name=region)
        self._bucket = evidence_bucket_name

    # -- cases ---------------------------------------------------------
    def save_case(self, case: Case) -> None:
        self._table.put_item(Item=_case_to_item(case))

    def get_case(self, case_id: str) -> Optional[Case]:
        resp = self._table.get_item(Key={"case_id": case_id})
        item = resp.get("Item")
        return _item_to_case(item) if item else None

    def open_cases_for_customer(self, customer_id: str) -> List[Case]:
        resp = self._table.query(
            IndexName="customer_id-index",
            KeyConditionExpression="customer_id = :c",
            ExpressionAttributeValues={":c": customer_id},
        )
        cases = [_item_to_case(item) for item in resp.get("Items", [])]
        return [c for c in cases if c.status == CaseStatus.OPEN]

    def all_cases(self) -> List[Case]:
        cases = []
        resp = self._table.scan()
        for item in resp.get("Items", []):
            if item["case_id"].startswith("IDEMP#"):
                continue
            cases.append(_item_to_case(item))
        return cases

    # -- idempotency -----------------------------------------------------
    def find_case_by_idempotency_key(self, idempotency_key: str) -> Optional[Case]:
        resp = self._table.get_item(Key={"case_id": f"IDEMP#{idempotency_key}"})
        marker = resp.get("Item")
        if not marker:
            return None
        return self.get_case(marker["real_case_id"])

    def register_idempotency_key(self, idempotency_key: str, case_id: str) -> None:
        self._table.put_item(Item={"case_id": f"IDEMP#{idempotency_key}", "real_case_id": case_id})

    # -- snapshots --------------------------------------------------------
    def _snapshot_key(self, snapshot_id: str) -> str:
        return f"snapshots/{snapshot_id}.json"

    def save_snapshot(self, snapshot: EvidenceSnapshot) -> None:
        key = self._snapshot_key(snapshot.snapshot_id)
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            raise SnapshotAlreadyExistsError(
                f"snapshot {snapshot.snapshot_id} already exists -- snapshots are write-once"
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "404":
                raise

        body = {
            "snapshot_id": snapshot.snapshot_id,
            "case_id": snapshot.case_id,
            "created_at": snapshot.created_at.isoformat(),
            "content_hash": snapshot.content_hash,
            "storage_uri": snapshot.storage_uri,
            "sources": [_to_json_safe(r) for r in snapshot.sources],
        }
        self._s3.put_object(
            Bucket=self._bucket, Key=key,
            Body=json.dumps(body).encode("utf-8"),
            ContentType="application/json",
        )

    def get_snapshot(self, snapshot_id: str) -> Optional[EvidenceSnapshot]:
        key = self._snapshot_key(snapshot_id)
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return None
            raise
        body = json.loads(resp["Body"].read())
        sources = tuple(
            EvidenceSourceResult(
                source=EvidenceSource(s["source"]),
                status=EvidenceStatus(s["status"]),
                evidence_id=s["evidence_id"],
                fetched_at=_parse_dt(s["fetched_at"]),
                timeout_ms=s["timeout_ms"],
                elapsed_ms=s["elapsed_ms"],
                data=s.get("data"),
                error=s.get("error"),
            )
            for s in body["sources"]
        )
        return EvidenceSnapshot(
            snapshot_id=body["snapshot_id"],
            case_id=body["case_id"],
            created_at=_parse_dt(body["created_at"]),
            sources=sources,
            content_hash=body["content_hash"],
            storage_uri=body["storage_uri"],
        )
