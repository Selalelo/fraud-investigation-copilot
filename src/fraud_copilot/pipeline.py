"""Orchestrates the pipeline: intake -> dedup/merge -> gather evidence -> freeze snapshot ->
compute indicators -> resolve entity graph -> classify scenario -> generate narrative ->
validate narrative -> assemble case (priority/SLA/evidence-incomplete warnings). Matches the
ResolveEntityGraph -> ClassifyScenario -> GenerateNarrative -> ValidateNarrative order of the
state machine (LLD.md sec 13).
"""
from __future__ import annotations

import uuid

from .dedup import classify
from .entity_graph import find_links
from .evidence_sources import SyntheticWorld, gather_all
from .indicators import compute_indicators, split_indicators
from .models import (
    Alert,
    Case,
    CaseStatus,
    DedupClassification,
    EvidenceStatus,
    LikelyScenario,
    NarrativeStatus,
    ValidationOutcome,
    sla_deadline_for,
)
from .narrative import LLMClient, generate_narrative
from .priority import compute_priority
from .scenario import classify_scenario
from .snapshot import build_snapshot
from .storage import Store
from .validator import validate


class DuplicateAlertError(Exception):
    """Raised when an alert is classified DUPLICATE -- the pipeline stops here, matching the
    state machine's RouteOnDedupResult -> LogDuplicateAndStop path (LLD.md sec 13)."""

    def __init__(self, existing_case: Case):
        self.existing_case = existing_case
        super().__init__(f"duplicate of case {existing_case.case_id}")


def process_alert(
    alert: Alert, world: SyntheticWorld, store: Store, llm_client: LLMClient = None
) -> Case:
    dedup_result = classify(alert, store)

    if dedup_result.classification == DedupClassification.DUPLICATE:
        raise DuplicateAlertError(dedup_result.existing_case)

    sources = gather_all(alert, world)
    incomplete_warnings = [
        f"Evidence incomplete: {r.source.value} {r.status.value.lower().replace('_', ' ')}"
        for r in sources
        if r.status != EvidenceStatus.FOUND
    ]

    if dedup_result.classification == DedupClassification.MERGED:
        case = dedup_result.existing_case
        case.alert_ids.append(alert.alert_id)
        if alert.beneficiary_id not in case.beneficiary_ids:
            case.beneficiary_ids.append(alert.beneficiary_id)
        case.amount = alert.amount
        case.immediate_action = alert.immediate_action
        if alert.data_source == "AMLSIM_REAL":
            # Upgrade-only: a case that ever touches real data stays flagged real, never
            # silently reverts to looking purely synthetic.
            case.data_source = "AMLSIM_REAL"
    else:
        case = Case(
            case_id=str(uuid.uuid4()),
            alert_ids=[alert.alert_id],
            customer_id=alert.customer_id,
            beneficiary_ids=[alert.beneficiary_id],
            amount=alert.amount,
            immediate_action=alert.immediate_action,
            snapshot_ids=[],
            latest_snapshot_id=None,
            priority=None,
            sla_deadline=None,
            likely_scenario=LikelyScenario.UNCLASSIFIED,
            scenario_evidence=[],
            indicators=[],
            counter_indicators=[],
            evidence_incomplete_warnings=[],
            linked_entities=[],
            narrative=None,
            narrative_status=None,
            status=CaseStatus.OPEN,
            created_at=alert.alert_time,
            data_source=alert.data_source,
            payment_rail=alert.payment_rail,
            payment_reference=alert.payment_reference,
            proxy_id=alert.proxy_id,
        )

    snapshot = build_snapshot(case.case_id, sources)
    store.save_snapshot(snapshot)  # raises SnapshotAlreadyExistsError if ever re-attempted
    case.snapshot_ids.append(snapshot.snapshot_id)
    case.latest_snapshot_id = snapshot.snapshot_id

    all_indicators = compute_indicators(alert, sources)
    indicators, counters = split_indicators(all_indicators)
    case.indicators = indicators
    case.counter_indicators = counters
    case.evidence_incomplete_warnings = incomplete_warnings

    case.priority = compute_priority(indicators, alert.immediate_action)
    case.sla_deadline = sla_deadline_for(case.priority, case.created_at)

    case.likely_scenario, case.scenario_evidence = classify_scenario(indicators, counters)

    narrative_text = generate_narrative(case.likely_scenario, indicators, counters, llm_client)
    validation_result = validate(narrative_text, indicators, counters, case.case_id)
    if validation_result.result == ValidationOutcome.PASS:
        case.narrative = narrative_text
        case.narrative_status = NarrativeStatus.VALIDATED
    else:
        case.narrative = None
        case.narrative_status = NarrativeStatus.UNAVAILABLE

    # Entity graph needs this case's own snapshot already in the store to include it as a node
    # for future cases' lookups, so save once, resolve links, then save again with them attached.
    store.save_case(case)
    store.register_idempotency_key(dedup_result.idempotency_key, case.case_id)
    case.linked_entities = find_links(case, store)
    store.save_case(case)
    return case
