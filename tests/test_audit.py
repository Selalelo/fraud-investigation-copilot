import pytest

from fraud_copilot.audit import AuditLog, InvalidDecisionError
from fraud_copilot.pipeline import process_alert
from fraud_copilot.storage import Store

from .factories import clean_world, make_alert


def test_decision_requires_reason_code():
    store = Store()
    case = process_alert(make_alert(), clean_world(), store)
    log = AuditLog()
    with pytest.raises(InvalidDecisionError):
        log.record_decision(case, store, "RELEASE", reason_code="", rationale="looks fine",
                             decided_by="inv1")


def test_decision_requires_rationale():
    store = Store()
    case = process_alert(make_alert(), clean_world(), store)
    log = AuditLog()
    with pytest.raises(InvalidDecisionError):
        log.record_decision(case, store, "RELEASE", reason_code="STANDARD_MONITORING",
                             rationale="   ", decided_by="inv1")


def test_valid_decision_recorded_with_snapshot_hash():
    store = Store()
    case = process_alert(make_alert(), clean_world(), store)
    log = AuditLog()
    record = log.record_decision(
        case, store, "RELEASE", reason_code="CUSTOMER_CONFIRMED_LEGITIMATE",
        rationale="Spoke to customer, confirmed transfer", decided_by="inv1",
    )
    snapshot = store.get_snapshot(case.latest_snapshot_id)
    assert record.snapshot_hash == snapshot.content_hash
    assert record.case_id == case.case_id


def test_audit_log_is_append_only():
    store = Store()
    case = process_alert(make_alert(), clean_world(), store)
    log = AuditLog()
    log.record_decision(case, store, "RELEASE", reason_code="STANDARD_MONITORING",
                         rationale="r1", decided_by="inv1")
    log.record_decision(case, store, "ESCALATE", reason_code="ESCALATED_TO_SPECIALIST",
                         rationale="r2", decided_by="inv2")
    assert len(log.entries_for_case(case.case_id)) == 2
    # no update/delete method exists on AuditLog -- only record_decision (append) and the
    # read accessors below.
    assert not hasattr(log, "update_decision")
    assert not hasattr(log, "delete_decision")


def test_evidence_views_tracked_and_attached_to_decision():
    store = Store()
    case = process_alert(make_alert(), clean_world(), store)
    log = AuditLog()
    log.record_evidence_view(case.case_id, "E4", "inv1")
    record = log.record_decision(case, store, "RELEASE", reason_code="STANDARD_MONITORING",
                                  rationale="checked device evidence", decided_by="inv1")
    assert len(record.evidence_views) == 1
    assert record.evidence_views[0].evidence_id == "E4"
