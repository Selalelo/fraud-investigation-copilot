"""Priority computation (LLD.md sec 5.3, post design-review fix).

Any HIGH-severity indicator forces HIGH priority regardless of immediate_action -- the original
formula only escalated via immediate_action == HOLD, so a HIGH-severity indicator (e.g. a SAFPS
grid hit) on an ALLOW payment fell through to LOW/24h, which is backwards.
"""
from __future__ import annotations

from typing import List

from .models import ImmediateAction, Indicator, Priority, Severity


def compute_priority(indicators: List[Indicator], immediate_action: ImmediateAction) -> Priority:
    severities = {i.severity for i in indicators if i.severity is not None}

    if Severity.HIGH in severities:
        return Priority.HIGH
    if immediate_action == ImmediateAction.HOLD and indicators:
        return Priority.HIGH
    if Severity.MEDIUM in severities:
        return Priority.MEDIUM
    if indicators and immediate_action in (ImmediateAction.STEP_UP, ImmediateAction.DELAY):
        return Priority.MEDIUM
    return Priority.LOW
