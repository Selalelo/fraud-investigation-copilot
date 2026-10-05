from fraud_copilot.evidence_sources import (
    FAIL_SENTINEL,
    NOT_AVAILABLE_SENTINEL,
    gather_all,
)
from fraud_copilot.models import EvidenceSource, EvidenceStatus

from .factories import clean_world, make_alert


def test_all_six_sources_found_in_clean_world():
    alert = make_alert()
    world = clean_world()
    results = gather_all(alert, world)
    assert len(results) == 6
    assert {r.source for r in results} == {
        EvidenceSource.CUSTOMER, EvidenceSource.TRANSACTION, EvidenceSource.BENEFICIARY,
        EvidenceSource.DEVICE, EvidenceSource.KYC, EvidenceSource.SAFPS,
    }
    assert all(r.status == EvidenceStatus.FOUND for r in results)
    # evidence IDs are unique and stable (E1..E6)
    assert [r.evidence_id for r in results] == ["E1", "E2", "E3", "E4", "E5", "E6"]


def test_missing_customer_is_not_found_not_silently_empty():
    alert = make_alert(customer_id="UNKNOWN-CUSTOMER")
    world = clean_world()
    results = gather_all(alert, world)
    customer_result = next(r for r in results if r.source == EvidenceSource.CUSTOMER)
    assert customer_result.status == EvidenceStatus.NOT_FOUND
    assert customer_result.data is None


def test_failed_source_never_blocks_other_sources():
    alert = make_alert(customer_id=FAIL_SENTINEL)
    world = clean_world()
    results = gather_all(alert, world)
    by_source = {r.source: r for r in results}
    assert by_source[EvidenceSource.CUSTOMER].status == EvidenceStatus.FAILED
    assert by_source[EvidenceSource.CUSTOMER].error is not None
    # every other source still resolved independently
    assert by_source[EvidenceSource.BENEFICIARY].status == EvidenceStatus.FOUND


def test_not_available_status_distinct_from_found_empty():
    alert = make_alert(proxy_id=NOT_AVAILABLE_SENTINEL, beneficiary_id=NOT_AVAILABLE_SENTINEL)
    world = clean_world()
    results = gather_all(alert, world)
    safps_result = next(r for r in results if r.source == EvidenceSource.SAFPS)
    assert safps_result.status == EvidenceStatus.NOT_AVAILABLE
    assert safps_result.data is None
