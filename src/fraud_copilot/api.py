"""Flask backend for the investigator web UI. Serves the static frontend at / and a small
JSON API under /api/. Two backends:
- create_app() (default, used by tests): in-memory Store, seeded at startup with the demo
  scenarios so the queue has real, varied data with no manual setup.
- create_app_aws(): DynamoStore backed by the real AWS resources deployed in infra/ (Stage B).
  Selected automatically when FRAUD_COPILOT_BACKEND=aws (see __main__ below); reads table/bucket
  names from FRAUD_COPILOT_CASES_TABLE / FRAUD_COPILOT_EVIDENCE_BUCKET / AWS_REGION env vars,
  defaulting to the names actually deployed by infra/.
"""
from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum

from flask import Flask, jsonify, request

from . import copilot, demo
from .audit import REASON_CODES, AuditLog, InvalidDecisionError
from .entity_graph import find_links
from .models import CaseStatus
from .outcomes import OutcomeStore
from .storage import Store

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "webapp")

app = Flask(__name__, static_folder=_STATIC_DIR, static_url_path="")

store = None
audit_log: AuditLog = None
outcome_store: OutcomeStore = None
copilot_llm_client = None  # None -> copilot.answer() uses its own offline MockToolCallingLLMClient


def create_app() -> Flask:
    global store, audit_log, outcome_store, copilot_llm_client
    store, _ = demo.build_store()
    audit_log = AuditLog()
    outcome_store = OutcomeStore(authorised_reviewers={"reviewer1", "supervisor1"})
    copilot_llm_client = None
    return app


def create_app_aws() -> Flask:
    """Points the same Flask app at the real deployed DynamoDB/S3 resources instead of an
    in-memory Store. Writes real data to the real account -- never called automatically by
    tests or imports, only via `FRAUD_COPILOT_BACKEND=aws python -m fraud_copilot.api`."""
    global store, audit_log, outcome_store, copilot_llm_client
    from .dynamo_store import DynamoStore

    store = DynamoStore(
        cases_table_name=os.environ.get("FRAUD_COPILOT_CASES_TABLE", "fraud-copilot-cases"),
        evidence_bucket_name=os.environ.get(
            "FRAUD_COPILOT_EVIDENCE_BUCKET", "fraud-copilot-evidence-snapshots-945323157686"
        ),
        region=os.environ.get("AWS_REGION", "us-east-1"),
    )

    if os.environ.get("FRAUD_COPILOT_MOCK_LLM") == "1":
        llm_client = None  # falls back to narrative.MockLLMClient inside generate_narrative
        copilot_llm_client = None  # falls back to copilot.MockToolCallingLLMClient
    else:
        from .narrative import BedrockLLMClient
        llm_client = BedrockLLMClient(region=os.environ.get("AWS_REGION", "us-east-1"))
        from .copilot import BedrockToolCallingLLMClient
        copilot_llm_client = BedrockToolCallingLLMClient(region=os.environ.get("AWS_REGION", "us-east-1"))

    demo.seed_store(store, llm_client=llm_client)
    audit_log = AuditLog()
    outcome_store = OutcomeStore(authorised_reviewers={"reviewer1", "supervisor1"})
    return app


def _json_safe(value):
    if is_dataclass(value):
        return {k: _json_safe(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


def _case_summary(case) -> dict:
    return {
        "case_id": case.case_id,
        "customer_id": case.customer_id,
        "beneficiary_ids": case.beneficiary_ids,
        "amount": case.amount,
        "immediate_action": case.immediate_action.value,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "priority": case.priority.value if case.priority else None,
        "sla_deadline": case.sla_deadline.isoformat() if case.sla_deadline else None,
        "likely_scenario": case.likely_scenario.value,
        "status": case.status.value,
        "indicator_count": len(case.indicators),
        "evidence_incomplete": bool(case.evidence_incomplete_warnings),
        "data_source": case.data_source,
    }


def _case_detail(case) -> dict:
    snapshot = store.get_snapshot(case.latest_snapshot_id) if case.latest_snapshot_id else None
    return {
        **_case_summary(case),
        "scenario_evidence": case.scenario_evidence,
        "indicators": [_json_safe(i) for i in case.indicators],
        "counter_indicators": [_json_safe(i) for i in case.counter_indicators],
        "evidence_incomplete_warnings": case.evidence_incomplete_warnings,
        "linked_entities": [_json_safe(l) for l in case.linked_entities],
        "narrative": case.narrative,
        "narrative_status": case.narrative_status.value if case.narrative_status else None,
        "snapshot_content_hash": snapshot.content_hash if snapshot else None,
        "snapshot_ids": case.snapshot_ids,
        "audit_history": [_json_safe(a) for a in audit_log.entries_for_case(case.case_id)],
    }


@app.get("/api/cases")
def list_cases():
    return jsonify([_case_summary(c) for c in store.all_cases()])


@app.get("/api/dashboard")
def dashboard():
    cases = list(store.all_cases())
    now = datetime.now(timezone.utc)
    stats = {
        "open": sum(1 for c in cases if c.status.value == "OPEN"),
        "decided": sum(1 for c in cases if c.status.value == "DECIDED"),
        "sla_overdue": sum(
            1 for c in cases
            if c.status.value == "OPEN" and c.sla_deadline and c.sla_deadline < now
        ),
        "high_priority": sum(1 for c in cases if c.priority and c.priority.value == "HIGH"),
    }
    recent_cases = sorted(cases, key=lambda c: c.created_at, reverse=True)[:5]
    return jsonify({
        "stats": stats,
        "recent_cases": [_case_summary(c) for c in recent_cases],
    })


@app.get("/api/cases/<case_id>")
def get_case(case_id):
    case = store.get_case(case_id)
    if case is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(_case_detail(case))


@app.get("/api/cases/<case_id>/evidence")
def get_case_evidence(case_id):
    """Raw evidence-source data for the Evidence tab -- the actual snapshot sources (LLD sec 3),
    not the computed indicator statements _case_detail already returns. A source with a
    non-FOUND status returns that status, never fabricated data."""
    case = store.get_case(case_id)
    if case is None:
        return jsonify({"error": "not found"}), 404
    if not case.latest_snapshot_id:
        return jsonify({"error": "no evidence snapshot for this case"}), 404
    snapshot = store.get_snapshot(case.latest_snapshot_id)
    if snapshot is None:
        return jsonify({"error": "snapshot not found"}), 404
    return jsonify({
        "snapshot_id": snapshot.snapshot_id,
        "content_hash": snapshot.content_hash,
        "created_at": snapshot.created_at.isoformat(),
        "sources": [_json_safe(r) for r in snapshot.sources],
    })


@app.get("/api/cases/<case_id>/copilot/intro")
def copilot_intro(case_id):
    case = store.get_case(case_id)
    if case is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "intro": copilot.intro_text(case),
        "suggested_questions": copilot.SUGGESTED_QUESTIONS,
    })


@app.post("/api/cases/<case_id>/copilot/ask")
def copilot_ask(case_id):
    case = store.get_case(case_id)
    if case is None:
        return jsonify({"error": "not found"}), 404
    body = request.get_json(force=True)
    question = body.get("question", "")
    if not question.strip():
        return jsonify({"error": "question is required"}), 400
    snapshot = store.get_snapshot(case.latest_snapshot_id) if case.latest_snapshot_id else None
    audit_entries = audit_log.entries_for_case(case_id)
    answer = copilot.answer(question, case, snapshot, audit_entries, copilot_llm_client)
    return jsonify({"answer": answer})


@app.get("/api/reason-codes")
def reason_codes():
    return jsonify(sorted(REASON_CODES))


@app.post("/api/cases/<case_id>/evidence-view")
def evidence_view(case_id):
    case = store.get_case(case_id)
    if case is None:
        return jsonify({"error": "not found"}), 404
    body = request.get_json(force=True)
    evidence_id = body.get("evidence_id")
    investigator_id = body.get("investigator_id", "investigator1")
    if not evidence_id:
        return jsonify({"error": "evidence_id is required"}), 400
    audit_log.record_evidence_view(case_id, evidence_id, investigator_id)
    return jsonify({"ok": True})


@app.post("/api/cases/<case_id>/decision")
def decision(case_id):
    case = store.get_case(case_id)
    if case is None:
        return jsonify({"error": "not found"}), 404
    body = request.get_json(force=True)
    try:
        record = audit_log.record_decision(
            case, store,
            decision=body.get("decision", ""),
            reason_code=body.get("reason_code", ""),
            rationale=body.get("rationale", ""),
            decided_by=body.get("investigator_id", "investigator1"),
        )
    except InvalidDecisionError as e:
        return jsonify({"error": str(e)}), 400

    case.status = CaseStatus.DECIDED
    store.save_case(case)
    return jsonify(_json_safe(record))


@app.get("/")
def index():
    return app.send_static_file("index.html")


if __name__ == "__main__":
    if os.environ.get("FRAUD_COPILOT_BACKEND") == "aws":
        create_app_aws()
    else:
        create_app()
    app.run(debug=True, port=5000)
