from fraud_copilot.models import Indicator, IndicatorKind, Severity, ValidationOutcome
from fraud_copilot.validator import validate


def _ind(id_, statement, evidence_ids=("E1",)):
    return Indicator(id=id_, kind=IndicatorKind.INDICATOR, statement=statement,
                      evidence_ids=evidence_ids, severity=Severity.HIGH)


def test_valid_narrative_passes():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is 17.0x the 12-month maximum", ("E2",))]
    narrative = "Amount is 17.0x the 12-month maximum [E2]."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.PASS


def test_uncited_sentence_rejected():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is 17.0x the 12-month maximum", ("E2",))]
    narrative = "The amount seems unusually high."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.FAIL
    assert result.failed_rule == "uncited_sentence"


def test_unknown_citation_rejected():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is 17.0x the 12-month maximum", ("E2",))]
    narrative = "Amount is 17.0x the 12-month maximum [E99]."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.FAIL
    assert result.failed_rule == "unknown_citation"


def test_number_mismatch_rejected():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is 17.0x the 12-month maximum", ("E2",))]
    narrative = "Amount is 25.0x the 12-month maximum [E2]."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.FAIL
    assert result.failed_rule == "number_mismatch"


def test_digit_inside_citation_tag_excluded_from_number_check():
    """The design-review fix: the '2' in [E2] must never be treated as a claimed number."""
    indicators = [_ind("IND-BENEFICIARY-EXTERNAL", "Beneficiary account is external to this bank", ("E2",))]
    narrative = "Beneficiary account is external to this bank [E2]."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.PASS


def test_number_format_normalised_currency_vs_plain():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is R85,000 above the customer's usual range", ("E2",))]
    narrative = "Amount is 85000 above the customer's usual range [E2]."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.PASS


def test_banned_phrase_rejected():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is 17.0x the 12-month maximum", ("E2",))]
    narrative = "Amount is 17.0x the 12-month maximum [E2]. This is likely fraud [E2]."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.FAIL
    assert result.failed_rule == "banned_phrase"


def test_directional_mismatch_rejected():
    indicators = [_ind("IND-AMOUNT-HIGH", "Amount is above the customer's usual range", ("E2",))]
    narrative = "Amount is below the customer's usual range [E2]."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.FAIL
    assert result.failed_rule == "directional_mismatch"


def test_counter_indicators_also_validated():
    counters = [_ind("CI-DEVICE-USUAL", "Login from usual device and usual location", ("E4",))]
    narrative = "Login from usual device and usual location [E4]."
    result = validate(narrative, [], counters, "CASE-1")
    assert result.result == ValidationOutcome.PASS


def test_empty_narrative_fails():
    result = validate("", [], [], "CASE-1")
    assert result.result == ValidationOutcome.FAIL


def test_injection_case_narrative_passes_because_it_only_cites_the_deterministic_indicator():
    """The design-review fix, end to end at the validator level: the injection indicator's
    statement has no raw customer text and no numbers, so it validates like any other fact."""
    indicators = [_ind(
        "IND-INJECTION-LIKE-TEXT",
        "Payment reference or beneficiary name contains text resembling an instruction",
        ("E2",),
    )]
    narrative = "Payment reference or beneficiary name contains text resembling an instruction [E2]."
    result = validate(narrative, indicators, [], "CASE-1")
    assert result.result == ValidationOutcome.PASS
