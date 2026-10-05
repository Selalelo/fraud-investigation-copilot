"""Tests DynamoStore's serialize/deserialize round-tripping against mocked AWS (moto) -- never
against real AWS resources. Skipped if boto3/moto aren't installed."""
import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

import boto3 as boto3_mod
from moto import mock_aws

from fraud_copilot.dynamo_store import DynamoStore
from fraud_copilot.models import CaseStatus, LikelyScenario, NarrativeStatus, PaymentRail, Priority
from fraud_copilot.pipeline import process_alert
from fraud_copilot.storage import SnapshotAlreadyExistsError

from .factories import clean_world, make_alert

TABLE_NAME = "test-cases"
BUCKET_NAME = "test-evidence-bucket"
REGION = "us-east-1"


@pytest.fixture
def dynamo_store():
    with mock_aws():
        dynamodb = boto3_mod.client("dynamodb", region_name=REGION)
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "case_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "case_id", "AttributeType": "S"},
                {"AttributeName": "customer_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "customer_id-index",
                "KeySchema": [{"AttributeName": "customer_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
                "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        s3 = boto3_mod.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET_NAME)

        yield DynamoStore(cases_table_name=TABLE_NAME, evidence_bucket_name=BUCKET_NAME, region=REGION)


def test_pipeline_round_trips_through_dynamo_store(dynamo_store):
    """The real proof: process_alert() runs completely unmodified against DynamoStore, same as
    against the in-memory Store."""
    case = process_alert(make_alert(amount=85000.0), clean_world(), dynamo_store)

    fetched = dynamo_store.get_case(case.case_id)
    assert fetched is not None
    assert fetched.case_id == case.case_id
    assert fetched.priority == Priority.HIGH
    assert fetched.status == CaseStatus.OPEN
    assert len(fetched.indicators) == len(case.indicators)
    assert {i.id for i in fetched.indicators} == {i.id for i in case.indicators}
    assert fetched.narrative == case.narrative
    assert fetched.narrative_status == case.narrative_status
    assert fetched.payment_rail == PaymentRail.PAYSHAP
    assert fetched.payment_reference == "rent"
    assert fetched.proxy_id == "0821234567"


def test_snapshot_round_trips_through_s3(dynamo_store):
    case = process_alert(make_alert(), clean_world(), dynamo_store)
    snapshot = dynamo_store.get_snapshot(case.latest_snapshot_id)
    assert snapshot is not None
    assert snapshot.snapshot_id == case.latest_snapshot_id
    assert len(snapshot.sources) == 6
    assert all(r.status.value == "FOUND" for r in snapshot.sources)


def test_snapshot_is_write_once_in_s3(dynamo_store):
    case = process_alert(make_alert(), clean_world(), dynamo_store)
    snapshot = dynamo_store.get_snapshot(case.latest_snapshot_id)
    with pytest.raises(SnapshotAlreadyExistsError):
        dynamo_store.save_snapshot(snapshot)


def test_idempotency_marker_round_trips(dynamo_store):
    alert = make_alert()
    case = process_alert(alert, clean_world(), dynamo_store)

    from fraud_copilot.dedup import compute_idempotency_key
    key = compute_idempotency_key(alert)
    found = dynamo_store.find_case_by_idempotency_key(key)
    assert found is not None
    assert found.case_id == case.case_id


def test_all_cases_excludes_idempotency_markers(dynamo_store):
    process_alert(make_alert(), clean_world(), dynamo_store)
    cases = dynamo_store.all_cases()
    assert len(cases) == 1
    assert not cases[0].case_id.startswith("IDEMP#")


def test_open_cases_for_customer_filters_by_status(dynamo_store):
    case = process_alert(make_alert(), clean_world(), dynamo_store)
    open_cases = dynamo_store.open_cases_for_customer(case.customer_id)
    assert len(open_cases) == 1

    case.status = CaseStatus.DECIDED
    dynamo_store.save_case(case)
    open_cases = dynamo_store.open_cases_for_customer(case.customer_id)
    assert open_cases == []
