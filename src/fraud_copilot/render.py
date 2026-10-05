"""Renders a Case as the case screen from HLD.md sec 5, as plain text or markdown -- the
Phase 3 CLI/markdown alternative to a full investigator web UI (same backend proof, far less
build time)."""
from __future__ import annotations

from .models import Case, ImmediateAction, NarrativeStatus

_ACTIONS = [
    "CONTACT CUSTOMER", "RELEASE", "BLOCK", "ESCALATE", "REQUEST INFO",
    "START STR", "GENERATE SAPS PDF",
]

# Plain-English explanation of what each typology label actually means, derived directly from
# scenario.py's own rule logic -- shown so an investigator never has to already know what
# "FIRST_PARTY" etc. means. UNCLASSIFIED has no scenario_evidence, so nothing to explain.
SCENARIO_DESCRIPTIONS = {
    "APP_SCAM": "Push payment scam pattern: a newly added beneficiary combined with an unusually large transfer.",
    "ACCOUNT_TAKEOVER": "Account takeover pattern: an unusual device or a recent SIM swap suggests this may not be the genuine customer.",
    "MULE": "Money mule pattern: funds received and rapidly passed through this account.",
    "FIRST_PARTY": "First-party risk pattern: an unusually large transfer from a long-standing customer, with no new beneficiary or device signal.",
}


def _sla_remaining(case: Case) -> str:
    if not case.sla_deadline:
        return "n/a"
    delta = case.sla_deadline - case.created_at
    minutes = int(delta.total_seconds() // 60)
    if minutes >= 60:
        return f"{minutes // 60}h {minutes % 60}min"
    return f"{minutes} min"


def render_case(case: Case) -> str:
    lines = []
    status_line = "PAYMENT HELD" if case.immediate_action == ImmediateAction.HOLD else case.immediate_action.value
    source_tag = " [REAL AMLSIM DATA]" if case.data_source == "AMLSIM_REAL" else ""
    lines.append(f"CASE #{case.case_id[:8]}     PRIORITY: {case.priority.value if case.priority else 'n/a'}  SLA {_sla_remaining(case)}{source_tag}")
    lines.append(f"R{case.amount:,.0f} transfer -- {status_line}")
    lines.append(f"Potential typology: {case.likely_scenario.value}" +
                 (f" (triggered by {', '.join(case.scenario_evidence)})" if case.scenario_evidence else ""))
    description = SCENARIO_DESCRIPTIONS.get(case.likely_scenario.value)
    if description:
        lines.append(description)
    for warning in case.evidence_incomplete_warnings:
        lines.append(f"! {warning}")
    lines.append("")

    lines.append("INDICATORS")
    if case.indicators:
        for i in case.indicators:
            cites = "".join(f"[{e}]" for e in i.evidence_ids)
            lines.append(f"  * {i.statement} ({i.severity.value if i.severity else 'n/a'})  {cites}")
    else:
        lines.append("  (none found)")
    lines.append("")

    lines.append("COUNTER-INDICATORS")
    if case.counter_indicators:
        for i in case.counter_indicators:
            cites = "".join(f"[{e}]" for e in i.evidence_ids)
            lines.append(f"  * {i.statement}  {cites}")
    else:
        lines.append("  (none found)")
    lines.append("")

    lines.append("LINKED ENTITIES (graph)")
    if case.linked_entities:
        for link in case.linked_entities:
            lines.append(f"  * {link.narrative_hint} ({link.hops}-hop, shared {link.shared_attribute.lower()})")
    else:
        lines.append("  (none found)")
    lines.append("")

    lines.append("AI NARRATIVE (all claims cited)")
    if case.narrative_status == NarrativeStatus.VALIDATED and case.narrative:
        lines.append(f"  {case.narrative}")
    else:
        lines.append("  AI narrative unavailable.")
    lines.append("")

    lines.append("ACTIONS")
    lines.append("  [" + "] [".join(_ACTIONS) + "]")
    lines.append("")
    lines.append("Reason code: [ required ]  Rationale: ___")

    return "\n".join(lines)


def render_case_markdown(case: Case) -> str:
    status_line = "PAYMENT HELD" if case.immediate_action == ImmediateAction.HOLD else case.immediate_action.value
    md = [
        f"# Case #{case.case_id[:8]}" + (" 🔴 REAL AMLSIM DATA" if case.data_source == "AMLSIM_REAL" else ""),
        "",
        f"**Priority:** {case.priority.value if case.priority else 'n/a'}  ",
        f"**SLA remaining:** {_sla_remaining(case)}  ",
        f"**Amount:** R{case.amount:,.0f} ({status_line})  ",
        f"**Potential typology:** {case.likely_scenario.value}"
        + (f" (triggered by {', '.join(case.scenario_evidence)})" if case.scenario_evidence else ""),
        "",
    ]
    scenario_description = SCENARIO_DESCRIPTIONS.get(case.likely_scenario.value)
    if scenario_description:
        md.insert(len(md) - 1, f"*{scenario_description}*  ")
    if case.evidence_incomplete_warnings:
        md.append("> ⚠ " + " / ".join(case.evidence_incomplete_warnings))
        md.append("")

    md.append("## Indicators")
    if case.indicators:
        for i in case.indicators:
            cites = "".join(f"`[{e}]`" for e in i.evidence_ids)
            md.append(f"- {i.statement} ({i.severity.value if i.severity else 'n/a'}) {cites}")
    else:
        md.append("_(none found)_")
    md.append("")

    md.append("## Counter-indicators")
    if case.counter_indicators:
        for i in case.counter_indicators:
            cites = "".join(f"`[{e}]`" for e in i.evidence_ids)
            md.append(f"- {i.statement} {cites}")
    else:
        md.append("_(none found)_")
    md.append("")

    md.append("## Linked entities (graph)")
    if case.linked_entities:
        for link in case.linked_entities:
            md.append(f"- {link.narrative_hint} ({link.hops}-hop, shared {link.shared_attribute.lower()})")
    else:
        md.append("_(none found)_")
    md.append("")

    md.append("## AI narrative (all claims cited)")
    if case.narrative_status == NarrativeStatus.VALIDATED and case.narrative:
        md.append(case.narrative)
    else:
        md.append("_AI narrative unavailable._")
    md.append("")

    md.append("## Actions")
    md.append(", ".join(f"**{a}**" for a in _ACTIONS))
    md.append("")
    md.append("Reason code: _required_ · Rationale: ___")

    return "\n".join(md)
