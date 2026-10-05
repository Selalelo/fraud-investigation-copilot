from fraud_copilot.models import ImmediateAction, Indicator, IndicatorKind, Priority, Severity
from fraud_copilot.priority import compute_priority


def _ind(severity):
    return Indicator(
        id="X", kind=IndicatorKind.INDICATOR, statement="x",
        evidence_ids=("E1",), severity=severity,
    )


def test_no_indicators_and_allow_is_low():
    assert compute_priority([], ImmediateAction.ALLOW) == Priority.LOW


def test_high_severity_indicator_forces_high_even_on_allow():
    # the exact hole the design review found: a HIGH-severity indicator (e.g. SAFPS hit) on an
    # ALLOW payment must not fall through to LOW/24h.
    assert compute_priority([_ind(Severity.HIGH)], ImmediateAction.ALLOW) == Priority.HIGH


def test_hold_with_any_indicator_is_high():
    assert compute_priority([_ind(Severity.LOW)], ImmediateAction.HOLD) == Priority.HIGH


def test_hold_with_no_indicators_is_low():
    assert compute_priority([], ImmediateAction.HOLD) == Priority.LOW


def test_medium_severity_indicator_is_medium():
    assert compute_priority([_ind(Severity.MEDIUM)], ImmediateAction.ALLOW) == Priority.MEDIUM


def test_step_up_with_low_indicator_is_medium():
    assert compute_priority([_ind(Severity.LOW)], ImmediateAction.STEP_UP) == Priority.MEDIUM


def test_low_severity_indicator_on_allow_is_low():
    assert compute_priority([_ind(Severity.LOW)], ImmediateAction.ALLOW) == Priority.LOW
