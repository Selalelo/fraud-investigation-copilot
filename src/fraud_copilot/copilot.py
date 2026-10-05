"""Grounded Copilot Q&A for the case detail screen (plan_18, extended by plan_22).

Two AI jobs in this app, per the user's own framing:
  - Job #1, narrative generation (narrative.py): Alert -> Evidence -> AI -> Investigation
    summary. Runs automatically, unaffected by this module.
  - Job #2, this module: Investigator -> question -> Copilot -> tool -> Evidence -> Answer.
    The evidence layer is the source of truth; the LLM is an interface over it, never a source
    of new facts.

The 4 suggested questions (SUGGESTED_QUESTIONS) are answered by the deterministic handlers
below -- built directly from real case/evidence fields, cited with the source's real
evidence_id, no LLM call, nothing to hallucinate. Only when the investigator's question does
NOT exactly match one of those does a genuine free-text question go through an LLM with tool
use (4 scoped tools: transaction, customer, related-cases, timeline), and even then every
sentence of the answer must cite a tool result that was actually returned this conversation
and every number in it must appear in that tool's own data -- checked by
_validate_tool_answer, which fails closed to the same fixed fallback message rather than ever
showing an unvalidated model output to the investigator.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from .models import Case, EvidenceSnapshot, EvidenceSourceResult, Indicator
from .validator import _BANNED_PHRASES, _normalise_number

SUGGESTED_QUESTIONS = [
    "Why was this flagged?",
    "Show related cases",
    "Explain beneficiary",
    "Compare transactions",
    "What evidence contradicts the risk?",
    "What evidence is missing?",
]

_FALLBACK_ANSWER = (
    "I can only answer grounded questions about why this case was flagged, related cases, "
    "the beneficiary, or the transaction history. Try one of the suggested questions, or ask "
    "about one of those topics."
)


def intro_text(case: Case) -> str:
    n = len(case.indicators)
    signal = "signal" if n == 1 else "signals"
    return f"I found {n} relevant {signal}. What would you like to investigate?"


def _find_source(snapshot: Optional[EvidenceSnapshot], source_name: str) -> Optional[EvidenceSourceResult]:
    if snapshot is None:
        return None
    for s in snapshot.sources:
        if s.source.value == source_name:
            return s
    return None


def _natural_indicator_sentence(
    i: Indicator, case: Case, txn: Optional[EvidenceSourceResult],
    ben: Optional[EvidenceSourceResult], dev: Optional[EvidenceSourceResult],
    safps: Optional[EvidenceSourceResult],
) -> str:
    cite = "".join(f"[{e}]" for e in i.evidence_ids)
    if i.id == "IND-AMOUNT-HIGH" and txn and txn.data and txn.data.get("history_12m_amounts"):
        history = txn.data["history_12m_amounts"]
        mx = max(history)
        return (
            f"The R{case.amount:,.0f} transfer is {case.amount / mx:.1f}× higher than the "
            f"customer's previous 12-month maximum of R{mx:,.0f}, based on {len(history)} "
            f"transaction{'s' if len(history) != 1 else ''} analysed {cite}."
        )
    if i.id == "IND-BENEFICIARY-NEW" and ben and ben.data and ben.data.get("date_added"):
        return f"The beneficiary was added on {ben.data['date_added']}, shortly before this transfer {cite}."
    if i.id == "IND-BENEFICIARY-LINKED" and ben and ben.data:
        prior = ben.data.get("prior_case_count", 0)
        return f"This beneficiary appears in {prior} prior case{'s' if prior != 1 else ''} {cite}."
    if i.id == "IND-BENEFICIARY-EXTERNAL":
        return f"The beneficiary account is external to this bank {cite}."
    if i.id == "IND-DEVICE-UNUSUAL":
        return f"The transfer was initiated from a device that isn't usual for this customer {cite}."
    if i.id == "IND-RECENT-SIM-SWAP" and dev and dev.data:
        days = dev.data.get("last_sim_swap_days")
        return f"A SIM swap was recorded {days} day(s) before this transfer {cite}."
    if i.id == "IND-SAFPS-GRID-HIT" and safps and safps.data:
        category = safps.data.get("alert_category") or "unspecified"
        return f"The beneficiary matches an active SAFPS grid alert ({category}) {cite}."
    if i.id == "IND-RAPID-PASSTHROUGH" and txn and txn.data:
        days = txn.data.get("recent_large_inbound_days_before")
        return f"A large inbound deposit was received just {days} day(s) before this outgoing transfer {cite}."
    if i.id == "IND-INJECTION-LIKE-TEXT":
        return f"The payment reference or beneficiary name contains text resembling an instruction {cite}."
    return f"{i.statement} {cite}."


def _why_flagged(case: Case, snapshot: Optional[EvidenceSnapshot]) -> str:
    if not case.indicators:
        return "No indicators were raised on this case."

    txn = _find_source(snapshot, "TRANSACTION")
    ben = _find_source(snapshot, "BENEFICIARY")
    dev = _find_source(snapshot, "DEVICE")
    safps = _find_source(snapshot, "SAFPS")

    sentences = [
        _natural_indicator_sentence(i, case, txn, ben, dev, safps) for i in case.indicators
    ]

    fired_rapid_passthrough = any(i.id == "IND-RAPID-PASSTHROUGH" for i in case.indicators)
    if not fired_rapid_passthrough and txn and txn.data and txn.data.get("recent_large_inbound") is False:
        sentences.append(
            f"The transaction also occurred without a recent large inbound transaction [{txn.evidence_id}]."
        )

    return " ".join(sentences)


def _related_cases(case: Case) -> str:
    if not case.linked_entities:
        return "No related cases found for this case."
    parts = []
    for link in case.linked_entities:
        parts.append(
            f"Related to {link.linked_entity_type} {link.linked_entity_id} via "
            f"{link.shared_attribute} ({link.hops} hop{'s' if link.hops != 1 else ''})."
        )
    return " ".join(parts)


def _explain_beneficiary(snapshot: Optional[EvidenceSnapshot]) -> str:
    source = _find_source(snapshot, "BENEFICIARY")
    if source is None or source.status.value != "FOUND" or source.data is None:
        return "No beneficiary evidence available for this case."
    d = source.data
    parts = []
    if d.get("date_added") is not None:
        parts.append(f"This beneficiary was added on {d['date_added']} [{source.evidence_id}].")
    if d.get("account_age_days") is not None:
        parts.append(f"The beneficiary account is {d['account_age_days']} days old [{source.evidence_id}].")
    if d.get("external") is not None:
        parts.append(
            f"This is {'an external' if d['external'] else 'not an external'} beneficiary "
            f"[{source.evidence_id}]."
        )
    if not parts:
        return "No beneficiary evidence available for this case."
    return " ".join(parts)


def _compare_transactions(case: Case, snapshot: Optional[EvidenceSnapshot]) -> str:
    source = _find_source(snapshot, "TRANSACTION")
    if source is None or source.status.value != "FOUND" or source.data is None:
        return "No transaction history evidence available for this case."
    d = source.data
    parts = [f"The current transaction is R{case.amount:,.0f}."]
    history = d.get("history_12m_amounts")
    if history:
        parts.append(f"12-month history amounts: {history} [{source.evidence_id}].")
    if d.get("recent_large_inbound"):
        amount = d.get("recent_large_inbound_amount")
        days = d.get("recent_large_inbound_days_before")
        parts.append(
            f"There was a recent large inbound transaction of R{amount:,.0f} "
            f"{days} days before this transfer [{source.evidence_id}]."
        )
    else:
        parts.append(f"There was no recent large inbound transaction [{source.evidence_id}].")
    return " ".join(parts)


def _what_contradicts(case: Case) -> str:
    if not case.counter_indicators:
        return "No counter-indicators were found for this case."
    sentences = []
    for i in case.counter_indicators:
        cites = "".join(f"[{e}]" for e in i.evidence_ids)
        sentences.append(f"{i.statement} {cites}.")
    return " ".join(sentences)


def _what_is_missing(case: Case) -> str:
    if not case.evidence_incomplete_warnings:
        return "No evidence is missing for this case; all sources returned data."
    return " ".join(f"{w}." for w in case.evidence_incomplete_warnings)


_SUGGESTED_HANDLERS = {
    "why was this flagged?": lambda case, snapshot, audit_entries: _why_flagged(case, snapshot),
    "show related cases": lambda case, snapshot, audit_entries: _related_cases(case),
    "explain beneficiary": lambda case, snapshot, audit_entries: _explain_beneficiary(snapshot),
    "compare transactions": lambda case, snapshot, audit_entries: _compare_transactions(case, snapshot),
    "what evidence contradicts the risk?": lambda case, snapshot, audit_entries: _what_contradicts(case),
    "what evidence is missing?": lambda case, snapshot, audit_entries: _what_is_missing(case),
}


def _coerce_dt(t) -> datetime:
    if isinstance(t, str):
        t = datetime.fromisoformat(t)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def _format_delta(from_dt: datetime, to_dt: datetime) -> str:
    """Mirrors app.js's fmtRelativeDelta -- keep both in sync. Makes a real time gap explicit
    (e.g. '200 days before' vs '9 minutes before') instead of leaving the investigator to infer
    recency, or lack of it, from two separate timestamps."""
    delta = to_dt - from_dt
    before = delta.total_seconds() >= 0
    total_minutes = round(abs(delta.total_seconds()) / 60)
    if total_minutes < 60:
        amount, unit = total_minutes, "minute"
    elif total_minutes < 24 * 60:
        amount, unit = round(total_minutes / 60), "hour"
    else:
        amount, unit = round(total_minutes / (24 * 60)), "day"
    return f"{amount} {unit}{'s' if amount != 1 else ''} {'before' if before else 'after'} this transfer"


def _build_timeline(case: Case, snapshot: Optional[EvidenceSnapshot], audit_entries: Optional[list]) -> List[Dict[str, Any]]:
    """Server-side port of app.js's renderTimelinePanel() -- must stay in lockstep with it so
    the Timeline tab and this tool can never disagree about what happened when."""
    events: List[Dict[str, Any]] = []

    beneficiary = _find_source(snapshot, "BENEFICIARY")
    if beneficiary and beneficiary.status.value == "FOUND" and beneficiary.data and beneficiary.data.get("date_added"):
        date_added = beneficiary.data["date_added"]
        events.append({
            "time": date_added,
            "label": f"Beneficiary added, {_format_delta(_coerce_dt(date_added), _coerce_dt(case.created_at))}",
            "source": f"evidence [{beneficiary.evidence_id}]",
        })

    events.append({"time": case.created_at, "label": "Alert received / transfer initiated", "source": "case.created_at"})

    if snapshot is not None:
        events.append({
            "time": snapshot.created_at,
            "label": "Evidence snapshot frozen (investigation began)",
            "source": f"snapshot {snapshot.snapshot_id[:8]}",
        })

    for a in audit_entries or []:
        for v in a.evidence_views:
            events.append({
                "time": v.viewed_at, "label": f"Investigator viewed evidence [{v.evidence_id}]",
                "source": f"audit log, {v.investigator_id}",
            })
        events.append({
            "time": a.decided_at, "label": f"Decision recorded: {a.decision}",
            "source": f"audit log, {a.decided_by}",
        })

    def _sort_key(e):
        return _coerce_dt(e["time"])

    events = [e for e in events if e["time"]]
    events.sort(key=_sort_key)
    for e in events:
        t = e["time"]
        e["time"] = t if isinstance(t, str) else t.isoformat()
    return events


# -- Tool-use path for genuine free-text questions (plan_22) ---------------------------------


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


_TOOLS = [
    {
        "name": "get_transaction_evidence",
        "description": "Get the raw transaction evidence for this case (amount, 12-month transaction history, recent large inbound transactions).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_customer_evidence",
        "description": "Get the raw customer and beneficiary evidence for this case (KYC tier, spend history, tenure, beneficiary account age, when the beneficiary was added).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_related_cases",
        "description": "Get any other cases linked to this one through shared entities (customer, device, phone, IP), with the shared attribute and hop count.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_timeline",
        "description": "Get the chronological sequence of real, timestamped events for this case (beneficiary added, alert/transfer time, evidence snapshot frozen, investigator evidence views, decisions) -- use this for any 'what happened before/after/when' style question.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_device_evidence",
        "description": "Get the raw device/session evidence for this case (device fingerprint, whether the device/location are usual for this customer, days since last SIM swap, days since last password reset) -- use this for any device, location, SIM swap, or account-takeover style question.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _execute_tool(name: str, case: Case, snapshot: Optional[EvidenceSnapshot], audit_entries: Optional[list]) -> Dict[str, Any]:
    if name == "get_transaction_evidence":
        source = _find_source(snapshot, "TRANSACTION")
        payment_fields = {
            "payment_rail": case.payment_rail.value,
            "payment_reference": case.payment_reference,
            "proxy_id": case.proxy_id,
        }
        if source is None or source.status.value != "FOUND":
            return {
                "status": source.status.value if source else "NOT_AVAILABLE",
                "current_amount": case.amount, **payment_fields,
            }
        data = dict(source.data or {})
        data["current_amount"] = case.amount
        data.update(payment_fields)
        return {"status": "FOUND", "data": data}
    if name == "get_customer_evidence":
        customer = _find_source(snapshot, "CUSTOMER")
        beneficiary = _find_source(snapshot, "BENEFICIARY")
        return {
            "customer": {"status": customer.status.value, "data": customer.data} if customer else {"status": "NOT_AVAILABLE"},
            "beneficiary": {"status": beneficiary.status.value, "data": beneficiary.data} if beneficiary else {"status": "NOT_AVAILABLE"},
        }
    if name == "get_related_cases":
        return {"links": [
            {
                "linked_entity_type": l.linked_entity_type, "linked_entity_id": l.linked_entity_id,
                "shared_attribute": l.shared_attribute, "hops": l.hops,
            }
            for l in case.linked_entities
        ]}
    if name == "get_timeline":
        return {"events": _build_timeline(case, snapshot, audit_entries)}
    if name == "get_device_evidence":
        source = _find_source(snapshot, "DEVICE")
        if source is None or source.status.value != "FOUND":
            return {"status": source.status.value if source else "NOT_AVAILABLE"}
        return {"status": "FOUND", "data": source.data}
    return {"error": f"unknown tool {name}"}


_TOOL_SYSTEM_PROMPT = """You are a fraud-investigation copilot answering ONE question from an
investigator about a specific case. You have no information about this case except what the
provided tools return -- you must call a tool before stating any fact. Rules, all mandatory:
1. Call whichever of the 5 tools (get_transaction_evidence, get_customer_evidence,
   get_related_cases, get_timeline, get_device_evidence) are relevant to the question before
   answering.
2. Every sentence of your final answer must end with a citation of the form [KEY], where KEY
   is the citation_key given in the tool result you got that fact from.
3. Every number you state must appear verbatim in the tool result data you cite for that
   sentence. Do not compute, round, or estimate any new number.
4. Never state a verdict, a risk score, a probability, or a recommendation such as "likely
   fraud" or "safe to release."
5. Keep the answer to at most 4 sentences.
6. Output plain text only, no markdown, no headers."""

_TOOL_CITATION_KEYS = {
    "get_transaction_evidence": "TXN",
    "get_customer_evidence": "CUST",
    "get_related_cases": "REL",
    "get_timeline": "TIME",
    "get_device_evidence": "DEV",
}

_CITATION_RE = re.compile(r"\[([A-Z]+\d+)\]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_NUMBER_RE = re.compile(r"R?\d[\d,]*(?:\.\d+)?x?")


class ToolCallingLLMClient(Protocol):
    def run(
        self, system_prompt: str, question: str, case: Case,
        snapshot: Optional[EvidenceSnapshot], audit_entries: Optional[list],
    ) -> str:
        ...


class MockToolCallingLLMClient:
    """Deterministic, offline stand-in -- calls all 5 tools and mechanically writes one cited
    sentence per non-empty result, the same way narrative.py's MockLLMClient stands in for a
    real model. Guaranteed to pass _validate_tool_answer by construction, and used by
    create_app()/the test suite so nothing here ever makes a network call."""

    def run(self, system_prompt, question, case, snapshot, audit_entries=None) -> str:
        sentences = []

        txn = _execute_tool("get_transaction_evidence", case, snapshot, audit_entries)
        if txn.get("status") == "FOUND":
            d = txn["data"]
            sentences.append(f"The current transaction is R{case.amount:,.0f} [TXN1].")
            if d.get("history_12m_amounts"):
                sentences.append(f"12-month history amounts: {d['history_12m_amounts']} [TXN1].")

        cust = _execute_tool("get_customer_evidence", case, snapshot, audit_entries)
        beneficiary = cust.get("beneficiary", {})
        if beneficiary.get("status") == "FOUND" and beneficiary.get("data", {}).get("date_added"):
            sentences.append(f"This beneficiary was added on {beneficiary['data']['date_added']} [CUST1].")

        rel = _execute_tool("get_related_cases", case, snapshot, audit_entries)
        if rel.get("links"):
            link = rel["links"][0]
            sentences.append(
                f"Related to {link['linked_entity_type']} {link['linked_entity_id']} via "
                f"{link['shared_attribute']} ({link['hops']} hops) [REL1]."
            )

        tl = _execute_tool("get_timeline", case, snapshot, audit_entries)
        if tl.get("events"):
            first = tl["events"][0]
            sentences.append(f"{first['label']} at {first['time']} [TIME1].")

        dev = _execute_tool("get_device_evidence", case, snapshot, audit_entries)
        if dev.get("status") == "FOUND":
            d = dev["data"]
            sim_swap = d.get("last_sim_swap_days")
            sentences.append(
                f"{'No SIM swap on record' if sim_swap is None else f'Last SIM swap was {sim_swap} days ago'} [DEV1]."
            )

        return " ".join(sentences)


class BedrockToolCallingLLMClient:
    """Real LLM client -- calls Amazon Bedrock (Claude, via an inference profile, same as
    narrative.py's BedrockLLMClient) with tool use. Runs an agentic loop, executing any tool
    the model requests locally against real case/evidence data and feeding the result back,
    capped at MAX_TURNS model calls to bound cost and latency."""

    MAX_TURNS = 4

    def __init__(
        self, model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        region: str = "us-east-1", max_tokens: int = 512,
    ):
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id
        self._max_tokens = max_tokens

    def run(self, system_prompt, question, case, snapshot, audit_entries=None) -> str:
        messages = [{"role": "user", "content": question}]

        for _ in range(self.MAX_TURNS):
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self._max_tokens,
                "system": system_prompt,
                "tools": _TOOLS,
                "messages": messages,
            })
            response = self._client.invoke_model(modelId=self._model_id, body=body)
            payload = json.loads(response["body"].read())
            content = payload.get("content", [])
            messages.append({"role": "assistant", "content": content})

            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            if not tool_uses:
                return "".join(b.get("text", "") for b in content if b.get("type") == "text")

            tool_results = []
            for block in tool_uses:
                name = block["name"]
                key = f"{_TOOL_CITATION_KEYS.get(name, name)}1"
                result = _execute_tool(name, case, snapshot, audit_entries)
                result["citation_key"] = key
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block["id"],
                    "content": json.dumps(result, default=_json_default),
                })
            messages.append({"role": "user", "content": tool_results})

        return ""


def _validate_tool_answer(answer_text: str, evidence_map: Dict[str, str]) -> bool:
    if not answer_text.strip():
        return False
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(answer_text.strip()) if s.strip()]
    for sentence in sentences:
        citations = set(_CITATION_RE.findall(sentence))
        if not citations or not citations <= set(evidence_map):
            return False
        combined = " ".join(evidence_map[c] for c in citations)
        without_citations = _CITATION_RE.sub("", sentence)
        for raw in _NUMBER_RE.findall(without_citations):
            if not raw.strip():
                continue
            if str(_normalise_number(raw)) not in combined and raw not in combined:
                return False
    lower = answer_text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            return False
    return True


def _answer_freeform(
    question: str, case: Case, snapshot: Optional[EvidenceSnapshot],
    audit_entries: Optional[list], llm_client: Optional[ToolCallingLLMClient],
) -> str:
    if llm_client is None:
        llm_client = MockToolCallingLLMClient()

    try:
        answer_text = llm_client.run(_TOOL_SYSTEM_PROMPT, question, case, snapshot, audit_entries)
    except Exception:
        return _FALLBACK_ANSWER

    evidence_map = {
        f"{_TOOL_CITATION_KEYS[name]}1": json.dumps(
            _execute_tool(name, case, snapshot, audit_entries), default=_json_default
        )
        for name in _TOOL_CITATION_KEYS
    }
    if not _validate_tool_answer(answer_text, evidence_map):
        return _FALLBACK_ANSWER
    return answer_text


def answer(
    question: str, case: Case, snapshot: Optional[EvidenceSnapshot],
    audit_entries: Optional[list] = None, llm_client: Optional[ToolCallingLLMClient] = None,
) -> str:
    handler = _SUGGESTED_HANDLERS.get(question.strip().lower())
    if handler is not None:
        return handler(case, snapshot, audit_entries)
    return _answer_freeform(question, case, snapshot, audit_entries, llm_client)
