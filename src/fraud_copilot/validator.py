"""Citation & number validator (LLD.md sec 10, post design-review fix).

Checks citation existence and number accuracy -- documented (LLD sec 10.1a) as NOT a full
semantic check: the directional-word check below is a best-effort heuristic, and the banned-
phrase list is a coarse filter, not a guarantee. See LLD.md sec 10.1a for the residual risks this
validator deliberately does not claim to close.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List

from .models import Indicator, ValidationOutcome, ValidationResult

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CITATION_RE = re.compile(r"\[E\d+\]")
_NUMBER_RE = re.compile(r"R?\d[\d,]*(?:\.\d+)?x?")

_BANNED_PHRASES = [
    "likely fraud", "fraud likely", "risk score", "recommend block",
    "recommend blocking", "safe to release", "high risk of fraud",
    "low risk of fraud", "should be blocked", "should be released",
]

_DIRECTIONAL_PAIRS = [
    ("above", "below"), ("more than", "fewer than"), ("before", "after"),
    ("higher", "lower"), ("increase", "decrease"), ("greater", "less"),
]
_DIRECTIONAL_OPPOSITE = {}
for _a, _b in _DIRECTIONAL_PAIRS:
    _DIRECTIONAL_OPPOSITE[_a] = _b
    _DIRECTIONAL_OPPOSITE[_b] = _a


def _normalise_number(raw: str) -> float:
    s = raw.strip()
    is_multiplier = s.endswith("x")
    if is_multiplier:
        s = s[:-1]
    s = s.replace("R", "").replace(",", "")
    return float(s)


def _numbers_excluding_citations(text: str) -> List[float]:
    without_citations = _CITATION_RE.sub("", text)
    return [_normalise_number(m) for m in _NUMBER_RE.findall(without_citations) if m.strip()]


def _statements_for_citations(citations: set, indicators: List[Indicator]) -> List[Indicator]:
    return [i for i in indicators if citations & set(i.evidence_ids)]


def validate(
    narrative: str,
    indicators: List[Indicator],
    counter_indicators: List[Indicator],
    case_id: str,
) -> ValidationResult:
    all_indicators = list(indicators) + list(counter_indicators)
    known_evidence_ids = {e for i in all_indicators for e in i.evidence_ids}

    def fail(rule: str) -> ValidationResult:
        return ValidationResult(
            case_id=case_id, result=ValidationOutcome.FAIL, failed_rule=rule,
            narrative_checked=narrative, validated_at=datetime.now(timezone.utc),
        )

    if not narrative.strip():
        return fail("uncited_sentence")

    sentences = [s for s in _SENTENCE_SPLIT_RE.split(narrative.strip()) if s.strip()]

    for sentence in sentences:
        citations = {m[1:-1] for m in _CITATION_RE.findall(sentence)}  # strip [ ] -> bare 'E2'
        if not citations:
            return fail("uncited_sentence")

        if not citations <= known_evidence_ids:
            return fail("unknown_citation")

        matched_indicators = _statements_for_citations(citations, all_indicators)
        combined_statement_text = " ".join(i.statement for i in matched_indicators)
        allowed_numbers = set(_numbers_excluding_citations(combined_statement_text))
        sentence_numbers = _numbers_excluding_citations(sentence)
        for n in sentence_numbers:
            if n not in allowed_numbers:
                return fail("number_mismatch")

        sentence_lower = sentence.lower()
        combined_lower = combined_statement_text.lower()
        for word, opposite in _DIRECTIONAL_OPPOSITE.items():
            if word in sentence_lower and opposite in combined_lower and word not in combined_lower:
                return fail("directional_mismatch")

    narrative_lower = narrative.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in narrative_lower:
            return fail("banned_phrase")

    return ValidationResult(
        case_id=case_id, result=ValidationOutcome.PASS, failed_rule=None,
        narrative_checked=narrative, validated_at=datetime.now(timezone.utc),
    )
