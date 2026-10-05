from fraud_copilot.models import IndicatorKind, LikelyScenario, Severity
from fraud_copilot.scenario import classify_scenario
from fraud_copilot.models import Indicator


def _ind(id_, kind=IndicatorKind.INDICATOR, severity=Severity.HIGH):
    return Indicator(id=id_, kind=kind, statement=id_, evidence_ids=("E1",), severity=severity if kind == IndicatorKind.INDICATOR else None)


def test_mule_evaluated_first_even_with_other_signals():
    # IND-RAPID-PASSTHROUGH present alongside device-unusual (which alone would suggest ATO) --
    # MULE must still win because it's evaluated first (design review: it was previously
    # evaluated after APP_SCAM and rarely fired).
    indicators = [_ind("IND-RAPID-PASSTHROUGH"), _ind("IND-DEVICE-UNUSUAL")]
    scenario, evidence = classify_scenario(indicators, [])
    assert scenario == LikelyScenario.MULE
    assert evidence == ["IND-RAPID-PASSTHROUGH"]


def test_account_takeover_when_device_indicator_and_no_usual_device_ci():
    indicators = [_ind("IND-DEVICE-UNUSUAL")]
    scenario, evidence = classify_scenario(indicators, [])
    assert scenario == LikelyScenario.ACCOUNT_TAKEOVER
    assert "IND-DEVICE-UNUSUAL" in evidence


def test_app_scam_when_device_counters_hold_but_beneficiary_and_amount_fire():
    indicators = [_ind("IND-BENEFICIARY-NEW"), _ind("IND-AMOUNT-HIGH")]
    counters = [_ind("CI-DEVICE-USUAL", kind=IndicatorKind.COUNTER_INDICATOR),
                _ind("CI-NO-CREDENTIAL-CHANGE", kind=IndicatorKind.COUNTER_INDICATOR)]
    scenario, evidence = classify_scenario(indicators, counters)
    assert scenario == LikelyScenario.APP_SCAM


def test_first_party_worded_as_consistent_with_and_names_rules():
    indicators = [_ind("IND-AMOUNT-HIGH")]
    counters = [_ind("CI-CUSTOMER-TENURE", kind=IndicatorKind.COUNTER_INDICATOR)]
    scenario, evidence = classify_scenario(indicators, counters)
    assert scenario == LikelyScenario.FIRST_PARTY
    assert set(evidence) == {"IND-AMOUNT-HIGH"}


def test_first_party_does_not_fire_if_device_indicator_also_present():
    indicators = [_ind("IND-AMOUNT-HIGH"), _ind("IND-DEVICE-UNUSUAL")]
    counters = [_ind("CI-CUSTOMER-TENURE", kind=IndicatorKind.COUNTER_INDICATOR)]
    scenario, _ = classify_scenario(indicators, counters)
    # falls to ACCOUNT_TAKEOVER instead, since a device indicator is present
    assert scenario == LikelyScenario.ACCOUNT_TAKEOVER


def test_unclassified_when_nothing_matches():
    scenario, evidence = classify_scenario([], [])
    assert scenario == LikelyScenario.UNCLASSIFIED
    assert evidence == []
