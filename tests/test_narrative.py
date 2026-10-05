from fraud_copilot.models import IndicatorKind, LikelyScenario, Severity, Indicator
from fraud_copilot.narrative import MockLLMClient, build_prompt, generate_narrative


def _ind(id_, statement, evidence_ids=("E1",), severity=Severity.HIGH, kind=IndicatorKind.INDICATOR):
    return Indicator(id=id_, kind=kind, statement=statement, evidence_ids=evidence_ids, severity=severity if kind == IndicatorKind.INDICATOR else None)


def test_prompt_never_contains_raw_free_text_fields():
    """The original design's prompt template interpolated payment_reference/beneficiary_name
    directly (QUOTED_CUSTOMER_DATA). The fixed prompt must never contain those field names or
    any raw customer free text -- only computed indicator statements."""
    indicators = [_ind("IND-INJECTION-LIKE-TEXT",
                        "Payment reference or beneficiary name contains text resembling an instruction",
                        severity=Severity.LOW)]
    prompt = build_prompt(LikelyScenario.UNCLASSIFIED, indicators, [])
    assert "QUOTED_CUSTOMER_DATA" not in prompt
    assert "payment_reference" not in prompt
    assert "beneficiary_name" not in prompt
    # the raw injected instruction text itself must never appear
    assert "ignore prior instructions" not in prompt.lower()


def test_generate_narrative_cites_every_sentence():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is 17.0x the 12-month maximum", evidence_ids=("E2",))]
    counters = [_ind("CI-CUSTOMER-TENURE", "Customer tenure 5 years, no prior cases",
                      evidence_ids=("E1",), kind=IndicatorKind.COUNTER_INDICATOR)]
    narrative = generate_narrative(LikelyScenario.FIRST_PARTY, indicators, counters, MockLLMClient())
    assert "[E2]" in narrative
    assert "[E1]" in narrative
    for sentence in narrative.split(". "):
        if sentence.strip():
            assert "[E" in sentence


def test_generate_narrative_includes_counter_indicators_not_just_indicators():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is 17.0x the 12-month maximum", evidence_ids=("E2",))]
    counters = [_ind("CI-DEVICE-USUAL", "Login from usual device and usual location",
                      evidence_ids=("E4",), kind=IndicatorKind.COUNTER_INDICATOR)]
    narrative = generate_narrative(LikelyScenario.APP_SCAM, indicators, counters, MockLLMClient())
    assert "usual device" in narrative.lower()


def test_generate_narrative_empty_when_no_indicators_at_all():
    narrative = generate_narrative(LikelyScenario.UNCLASSIFIED, [], [], MockLLMClient())
    assert narrative == ""
