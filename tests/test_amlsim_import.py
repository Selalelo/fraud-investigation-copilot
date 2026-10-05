"""Tests the AMLSim importer against a REAL local simulator run (third_party/AMLSim/outputs/sample),
not synthetic fixtures. Skipped automatically if that output doesn't exist (e.g. CI without the
Java/Maven toolchain) -- see README.md for how to (re)generate it."""
import os

import pytest

from fraud_copilot.amlsim_import import (
    build_customer_record,
    build_world_and_alert_from_amlsim,
    find_sar_fan_in_group,
    load_amlsim_output,
)
from fraud_copilot.models import LikelyScenario
from fraud_copilot.pipeline import process_alert
from fraud_copilot.storage import Store

AMLSIM_OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "third_party", "AMLSim", "outputs", "sample"
)

pytestmark = pytest.mark.skipif(
    not os.path.isfile(os.path.join(AMLSIM_OUTPUT_DIR, "accounts.csv")),
    reason="third_party/AMLSim/outputs/sample not present -- run the AMLSim toolchain first (see README.md)",
)


def test_load_amlsim_output_parses_real_files():
    data = load_amlsim_output(AMLSIM_OUTPUT_DIR)
    assert len(data.accounts) > 0
    assert len(data.transactions) > 0
    assert any(row for rows in data.alert_membership.values() for row in rows)


def test_prior_case_count_reflects_real_alert_membership():
    data = load_amlsim_output(AMLSIM_OUTPUT_DIR)
    group = find_sar_fan_in_group(data)
    assert group is not None
    record = build_customer_record(data, group["collector_account"])
    assert record.prior_case_count >= 1  # this account really is in >=1 AMLSim alert group


def test_real_fan_in_group_found():
    data = load_amlsim_output(AMLSIM_OUTPUT_DIR)
    group = find_sar_fan_in_group(data)
    assert group is not None
    assert group["collector_account"] in data.accounts
    assert group["outbound_tx"]["orig_acct"] == group["collector_account"]


def test_pipeline_classifies_real_amlsim_mule_pattern_as_mule():
    """The end-to-end proof: a real simulated fan-in collector pattern, run through the
    unmodified pipeline, is classified consistent with MULE via IND-RAPID-PASSTHROUGH -- not
    a hand-crafted fixture engineered to pass."""
    alert, world = build_world_and_alert_from_amlsim(AMLSIM_OUTPUT_DIR)
    store = Store()
    case = process_alert(alert, world, store)

    indicator_ids = {i.id for i in case.indicators}
    assert "IND-RAPID-PASSTHROUGH" in indicator_ids
    assert case.likely_scenario == LikelyScenario.MULE
    assert "IND-RAPID-PASSTHROUGH" in case.scenario_evidence


def test_amlsim_case_is_tagged_as_real_data_not_synthetic():
    """The UI/render provenance tag this enables: a real-AMLSim case must never be visually
    indistinguishable from the hand-crafted demo fixtures."""
    alert, world = build_world_and_alert_from_amlsim(AMLSIM_OUTPUT_DIR)
    assert alert.data_source == "AMLSIM_REAL"

    store = Store()
    case = process_alert(alert, world, store)
    assert case.data_source == "AMLSIM_REAL"
