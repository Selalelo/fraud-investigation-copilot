import pytest

from fraud_copilot.evidence_sources import gather_all
from fraud_copilot.snapshot import build_snapshot, content_hash
from fraud_copilot.storage import SnapshotAlreadyExistsError, Store

from .factories import clean_world, make_alert


def test_content_hash_is_deterministic_for_same_input():
    alert = make_alert()
    world = clean_world()
    sources = gather_all(alert, world)
    assert content_hash(sources) == content_hash(sources)


def test_content_hash_changes_when_data_changes():
    alert = make_alert()
    world = clean_world()
    sources_a = gather_all(alert, world)
    world.customers["CUST-1"].tenure_years = 0.5
    sources_b = gather_all(alert, world)
    assert content_hash(sources_a) != content_hash(sources_b)


def test_snapshot_is_write_once():
    alert = make_alert()
    world = clean_world()
    sources = gather_all(alert, world)
    snapshot = build_snapshot("CASE-1", sources)
    store = Store()
    store.save_snapshot(snapshot)
    with pytest.raises(SnapshotAlreadyExistsError):
        store.save_snapshot(snapshot)


def test_snapshot_records_content_hash_and_storage_uri():
    alert = make_alert()
    world = clean_world()
    sources = gather_all(alert, world)
    snapshot = build_snapshot("CASE-1", sources)
    assert snapshot.content_hash
    assert snapshot.storage_uri.startswith("local://snapshots/")
    assert len(snapshot.sources) == 6
