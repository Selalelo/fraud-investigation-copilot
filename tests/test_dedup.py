from datetime import timedelta

from fraud_copilot.dedup import classify, compute_idempotency_key
from fraud_copilot.models import CaseStatus, DedupClassification
from fraud_copilot.pipeline import DuplicateAlertError, process_alert
from fraud_copilot.storage import Store

from .factories import NOW, clean_world, make_alert


def test_idempotency_key_delimited_no_collision():
    a = make_alert(customer_id="12", transaction_id="3459", alert_reason="x")
    b = make_alert(customer_id="123", transaction_id="459", alert_reason="x")
    assert compute_idempotency_key(a) != compute_idempotency_key(b)


def test_new_alert_classified_new_case():
    store = Store()
    result = classify(make_alert(), store)
    assert result.classification == DedupClassification.NEW_CASE


def test_same_alert_again_is_duplicate_of_open_case():
    store = Store()
    world = clean_world()
    alert = make_alert()
    case = process_alert(alert, world, store)

    result = classify(alert, store)
    assert result.classification == DedupClassification.DUPLICATE
    assert result.existing_case.case_id == case.case_id


def test_duplicate_check_also_covers_closed_cases():
    store = Store()
    world = clean_world()
    alert = make_alert()
    case = process_alert(alert, world, store)
    case.status = CaseStatus.DECIDED
    store.save_case(case)

    result = classify(alert, store)
    assert result.classification == DedupClassification.DUPLICATE


def test_second_alert_same_customer_within_window_is_merged():
    store = Store()
    world = clean_world()
    first = make_alert(alert_id="ALERT-1", transaction_id="TXN-1")
    process_alert(first, world, store)

    second = make_alert(
        alert_id="ALERT-2", transaction_id="TXN-2",
        alert_time=NOW + timedelta(minutes=10),
    )
    result = classify(second, store)
    assert result.classification == DedupClassification.MERGED


def test_merge_appends_new_snapshot_without_mutating_prior_one():
    store = Store()
    world = clean_world()
    first = make_alert(alert_id="ALERT-1", transaction_id="TXN-1")
    case = process_alert(first, world, store)
    first_snapshot_id = case.latest_snapshot_id
    first_snapshot = store.get_snapshot(first_snapshot_id)

    second = make_alert(
        alert_id="ALERT-2", transaction_id="TXN-2",
        alert_time=NOW + timedelta(minutes=10),
    )
    merged_case = process_alert(second, world, store)

    assert merged_case.case_id == case.case_id
    assert len(merged_case.snapshot_ids) == 2
    assert first_snapshot_id in merged_case.snapshot_ids
    assert merged_case.latest_snapshot_id != first_snapshot_id
    # the original snapshot object is untouched
    assert store.get_snapshot(first_snapshot_id) is first_snapshot


def test_duplicate_alert_raises_and_does_not_gather_evidence_again():
    store = Store()
    world = clean_world()
    alert = make_alert()
    case = process_alert(alert, world, store)

    try:
        process_alert(alert, world, store)
        assert False, "expected DuplicateAlertError"
    except DuplicateAlertError as e:
        assert e.existing_case.case_id == case.case_id
    # no second snapshot was created
    assert len(case.snapshot_ids) == 1
