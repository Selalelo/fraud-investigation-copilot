from datetime import timedelta

from fraud_copilot.models import CaseStatus, ImmediateAction, LikelyScenario, NarrativeStatus, Priority
from fraud_copilot.pipeline import process_alert
from fraud_copilot.storage import Store

from .factories import NOW, clean_world, make_alert


def test_end_to_end_high_risk_case():
    """The design's worked example: R85,000 transfer, beneficiary added 14 min ago,
    unusual device, held by the bank -- should produce a HIGH priority case with populated
    indicators, counter-indicators, and no evidence-incomplete warnings."""
    store = Store()
    world = clean_world()
    world.beneficiaries["BEN-1"].date_added = NOW - timedelta(minutes=14)
    world.devices["CUST-1"].is_usual_device = False
    world.devices["CUST-1"].is_usual_location = False

    alert = make_alert(amount=85000.0)
    case = process_alert(alert, world, store)

    assert case.status == CaseStatus.OPEN
    assert case.priority == Priority.HIGH
    assert case.sla_deadline is not None
    # unusual device + no CI-DEVICE-USUAL -> consistent with ACCOUNT_TAKEOVER (LLD sec 8 #2)
    assert case.likely_scenario == LikelyScenario.ACCOUNT_TAKEOVER
    assert case.scenario_evidence  # names the triggering rule(s)
    assert case.narrative_status == NarrativeStatus.VALIDATED
    assert case.narrative is not None
    assert "[E" in case.narrative  # every claim cited

    indicator_ids = {i.id for i in case.indicators}
    assert "IND-AMOUNT-HIGH" in indicator_ids
    assert "IND-BENEFICIARY-NEW" in indicator_ids
    assert "IND-DEVICE-UNUSUAL" in indicator_ids

    counter_ids = {i.id for i in case.counter_indicators}
    assert "CI-CUSTOMER-TENURE" in counter_ids  # long tenure still shows even on a HIGH case

    assert case.evidence_incomplete_warnings == []
    assert len(case.snapshot_ids) == 1


def test_evidence_incomplete_warning_surfaced_on_case():
    store = Store()
    world = clean_world()
    del world.devices["CUST-1"]  # device source will be NOT_FOUND

    alert = make_alert()
    case = process_alert(alert, world, store)

    assert any("device" in w.lower() for w in case.evidence_incomplete_warnings)


def test_missing_evidence_does_not_silently_read_as_clean():
    """A NOT_FOUND device source must not produce the device counter-indicators -- silence
    must never look like a clean result (design sec 3.3)."""
    store = Store()
    world = clean_world()
    del world.devices["CUST-1"]

    alert = make_alert()
    case = process_alert(alert, world, store)

    counter_ids = {i.id for i in case.counter_indicators}
    assert "CI-DEVICE-USUAL" not in counter_ids
    assert "CI-NO-CREDENTIAL-CHANGE" not in counter_ids
    assert any("device" in w.lower() for w in case.evidence_incomplete_warnings)


def test_low_risk_case_gets_low_priority():
    store = Store()
    world = clean_world()
    alert = make_alert(amount=1500.0, immediate_action=ImmediateAction.ALLOW)
    case = process_alert(alert, world, store)
    assert case.priority == Priority.LOW
