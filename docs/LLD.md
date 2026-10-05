# 1. Low-Level Design — Fraud Investigation Copilot

Companion to `HLD.md`. Defines the concrete schemas, rule logic, prompt, validator, and state
machine that Phase 1-4 implement. All examples use synthetic data.

## 2. Alert Schema

```json
{
  "alert_id": "string, source system's native ID",
  "idempotency_key": "string, dedup key (native or derived)",
  "customer_id": "string",
  "transaction_id": "string",
  "amount": "decimal, ZAR",
  "beneficiary_id": "string",
  "beneficiary_name": "string, free text as supplied by the customer/beneficiary record -- untrusted",
  "beneficiary_bank": "string, ISO bank code or 'THIS_BANK'",
  "payment_rail": "enum: RTC | PAYSHAP | EFT | INTERNAL",
  "proxy_id": "string | null, ShapID for PAYSHAP payments, else null",
  "payment_reference": "string, free text as supplied by the customer -- untrusted",
  "alert_reason": "string, e.g. 'unusual_transaction'",
  "immediate_action": "enum: HOLD | STEP_UP | DELAY | ALLOW",
  "alert_time": "ISO 8601 timestamp",
  "received_time": "ISO 8601 timestamp"
}
```

### 2.1 Idempotency & merge rule

| # | Rule |
|---|------|
| 1 | `idempotency_key` = native key if the source provides one, else `sha256(customer_id + "\|" + transaction_id + "\|" + alert_reason)` -- delimited, never plain concatenation, so e.g. `customer_id="12", transaction_id="3459"` cannot collide with `customer_id="123", transaction_id="459"` |
| 2 | An alert whose `idempotency_key` already exists on **any** case -- open or closed -- is dropped and logged as a duplicate against that case; dedup is not time-limited to open cases |
| 3 | An alert for a `customer_id` with an existing **open** case, arriving within the merge window (default 30 min) of that case's last alert, is attached to the existing case (see §13's `MERGED` branch) rather than opening a new one |

## 3. Evidence Source Result Schema

```json
{
  "source": "enum: CUSTOMER | TRANSACTION | BENEFICIARY | DEVICE | KYC | SAFPS",
  "status": "enum: FOUND | NOT_FOUND | NOT_AVAILABLE | FAILED",
  "evidence_id": "string, e.g. 'E1'",
  "fetched_at": "ISO 8601 timestamp",
  "timeout_ms": "int, configured timeout for this source",
  "elapsed_ms": "int, actual call duration",
  "data": "object | null, source-specific payload; null unless status == FOUND",
  "error": "string | null, present only when status == FAILED"
}
```

### 3.1 Six mock evidence sources (Phase 1)

| # | Source | Example fields in `data` | Timeout |
|---|--------|---------------------------|---------|
| 1 | Customer | tenure, KYC tier, historical monthly spend range, prior cases | 2000 ms |
| 2 | Transaction | 12-month transaction history, amount percentile vs. history, recent large inbound (amount + days before this alert) | 2000 ms |
| 3 | Beneficiary | account age, `external` flag, date added, appearances in prior cases | 2000 ms |
| 4 | Device | device fingerprint, is-usual-device flag, geolocation, last SIM swap / password reset | 2000 ms |
| 5 | KYC | identity verification status, last updated | 2000 ms |
| 6 | SAFPS **(mock)** | whether the beneficiary account/ShapID matches an active alert on the South African Fraud Prevention Service grid, alert category, date added to grid | 2000 ms |

**SAFPS is a mock source in this design.** Real programmatic (API) access to the SAFPS grid has
not been verified as part of this research -- treat it as a placeholder for a real integration to
be confirmed later, not a documented, available data-sharing API.

SAFPS fills the industry data-sharing slot the source design reserves but leaves empty
(`fraud-investigation-copilot.md` §3.4 — "design a slot for industry data sharing (for example,
via SABRIC), even if it is empty at launch"). Like every other source, a SAFPS `FOUND` result is
evidence with an evidence ID, not an automatic verdict — a grid hit becomes an indicator (§5.2),
it does not itself decide anything.

### 3.2 Status semantics

| # | Status | Meaning |
|---|--------|---------|
| 1 | `FOUND` | Source responded within timeout with data |
| 2 | `NOT_FOUND` | Source responded within timeout; the entity genuinely has no record (e.g. new customer) |
| 3 | `NOT_AVAILABLE` | Source is known to be out of scope for this case (e.g. external beneficiary, no data-sharing agreement) |
| 4 | `FAILED` | Source call errored or exceeded its timeout |

`NOT_FOUND`, `NOT_AVAILABLE`, and `FAILED` are all distinct from `FOUND` with empty data — the
pipeline never collapses "no data" into "no news."

## 4. Evidence Snapshot Schema

```json
{
  "snapshot_id": "string, UUID",
  "case_id": "string",
  "created_at": "ISO 8601 timestamp",
  "sources": ["EvidenceSourceResult, one per source"],
  "content_hash": "string, sha256 over the canonical JSON of `sources`",
  "storage_uri": "string, s3://bucket/key (S3 Object Lock, write-once)"
}
```

Snapshots are written once and never updated; a later re-fetch produces a new snapshot tied to a
new case, never a mutation of this one (US-C.1).

## 5. Indicator & Counter-Indicator Engine

### 5.1 Indicator schema

```json
{
  "id": "string, e.g. 'IND-AMOUNT-HIGH'",
  "kind": "enum: INDICATOR | COUNTER_INDICATOR",
  "statement": "string, deterministic fact, e.g. 'Amount is 10.6x the 12-month maximum'",
  "evidence_ids": ["string, e.g. ['E1']"],
  "severity": "enum: LOW | MEDIUM | HIGH, indicators only"
}
```

### 5.2 Rule set (MVP)

Every indicator rule now carries an explicit severity — the earlier version left severity unset
on 9 of 10 rules, which silently broke priority computation (§5.3).

| # | Rule ID | Kind | Severity | Logic | Evidence source |
|---|---------|------|----------|-------|------------------|
| 1 | `IND-AMOUNT-HIGH` | Indicator | HIGH | `amount / max(transaction.history_12m.amounts) >= 3` | TRANSACTION |
| 2 | `IND-BENEFICIARY-NEW` | Indicator | MEDIUM | `alert_time - beneficiary.date_added <= 60 min` | BENEFICIARY |
| 3 | `IND-BENEFICIARY-LINKED` | Indicator | HIGH | `beneficiary.prior_case_count >= 1` -- flags a known-bad **destination** account; this is not the MULE scenario signal, see §8 | BENEFICIARY |
| 4 | `IND-BENEFICIARY-EXTERNAL` | Indicator | LOW | `beneficiary.external == true` | BENEFICIARY |
| 5 | `IND-DEVICE-UNUSUAL` | Indicator | MEDIUM | `device.is_usual_device == false` | DEVICE |
| 6 | `IND-RECENT-SIM-SWAP` | Indicator | HIGH | `device.last_sim_swap_days <= 7` | DEVICE |
| 7 | `CI-DEVICE-USUAL` | Counter-indicator | n/a | `device.is_usual_device == true AND device.is_usual_location == true` | DEVICE |
| 8 | `CI-NO-CREDENTIAL-CHANGE` | Counter-indicator | n/a | `device.last_sim_swap_days IS NULL AND device.last_password_reset_days IS NULL` | DEVICE |
| 9 | `CI-CUSTOMER-TENURE` | Counter-indicator | n/a | `customer.tenure_years >= 3 AND customer.prior_case_count == 0` | CUSTOMER |
| 10 | `IND-SAFPS-GRID-HIT` | Indicator | HIGH | `safps.grid_match == true` | SAFPS (mock) |
| 11 | `IND-RAPID-PASSTHROUGH` | Indicator | HIGH | `transaction.recent_large_inbound == true AND transaction.recent_large_inbound_days_before <= 3` -- this customer's own account received a large deposit shortly before sending this transfer out; the actual MULE signal, see §8 | TRANSACTION |
| 12 | `IND-INJECTION-LIKE-TEXT` | Indicator | LOW (informational — not a fraud-severity signal, drives narrative safety not priority) | `payment_reference` or `beneficiary_name` matches a deterministic instruction-pattern check (imperative verbs directed at an assistant, e.g. "ignore", "disregard", "summarise as", phrased as a command) | ALERT (computed directly from the alert payload, not a fetched evidence source) |

A rule that depends on a source whose status is not `FOUND` does not fire (neither indicator nor
counter-indicator) — it is omitted, and the missing-evidence warning (US-B.1) covers the gap
instead of a false negative/positive.

`IND-INJECTION-LIKE-TEXT` exists specifically so the LLM prompt (§9) never needs the raw
`payment_reference`/`beneficiary_name` text — see §9 for how this closes the validator deadlock in
the original design.

### 5.3 Priority computation

The original formula only escalated to HIGH via `immediate_action == HOLD`, so a HIGH-severity
indicator (e.g. a SAFPS grid hit) on a payment the bank's own rules already `ALLOW`ed fell through
to LOW/24-hour SLA — backwards, since that is exactly the case an investigator needs to catch fast
before more damage is done. Fixed:

```text
priority = HIGH   if any HIGH-severity indicator fired
priority = HIGH   if immediate_action == HOLD and any indicator (any severity) fired
priority = MEDIUM if any MEDIUM-severity indicator fired
priority = MEDIUM if any indicator fired and immediate_action in (STEP_UP, DELAY)
priority = LOW    otherwise (no indicators fired, or only LOW-severity ones, and immediate_action == ALLOW)
```

Evaluated top-to-bottom, first match wins. SLA timer: `HIGH` = 60 min, `MEDIUM` = 4 hours,
`LOW` = 24 hours from case creation.

## 6. Case Schema

```json
{
  "case_id": "string, UUID",
  "alert_ids": ["string, merged alerts"],
  "customer_id": "string",
  "snapshot_ids": ["string, FK -> EvidenceSnapshot, ordered oldest to newest -- one per merge, each individually immutable"],
  "latest_snapshot_id": "string, FK -> EvidenceSnapshot, the snapshot indicators/narrative/priority are currently computed from",
  "priority": "enum: HIGH | MEDIUM | LOW",
  "sla_deadline": "ISO 8601 timestamp",
  "likely_scenario": "enum: ACCOUNT_TAKEOVER | APP_SCAM | MULE | FIRST_PARTY | UNCLASSIFIED",
  "scenario_evidence": ["string, rule ID(s) that produced likely_scenario, e.g. ['IND-RAPID-PASSTHROUGH'] -- see §8"],
  "indicators": ["Indicator, kind == INDICATOR"],
  "counter_indicators": ["Indicator, kind == COUNTER_INDICATOR"],
  "evidence_incomplete_warnings": ["string, one per non-FOUND source"],
  "linked_entities": ["GraphLink, see section 7.2"],
  "narrative": "string | null",
  "narrative_status": "enum: VALIDATED | UNAVAILABLE",
  "status": "enum: OPEN | DECIDED",
  "created_at": "ISO 8601 timestamp"
}
```

`snapshot_ids`/`latest_snapshot_id` resolve the earlier contradiction between §4's "a snapshot is
write-once, a re-fetch produces a new snapshot tied to a new case" and §2.1's merge rule attaching
a later alert to the *existing* case: a merge (§13's `MERGED` branch) gathers a fresh, independently
immutable snapshot and appends it to this same case's `snapshot_ids`, rather than mutating the
original snapshot or forcing a new case. Every past snapshot stays exactly as originally frozen;
`indicators`/`narrative`/`priority` are always recomputed from `latest_snapshot_id`, and the audit
record (§11) references whichever snapshot was current at the time of each decision.

### 6.1 SAPS Evidence PDF (Investigator Action)

An investigator-triggered export, not an automated dispatch — same pattern as the existing case
actions (`HLD.md` §5), requiring the investigator to explicitly request it (no reason code
required, since it produces evidence for the customer rather than committing a fraud decision).

```json
{
  "case_id": "string",
  "generated_by": "string, investigator ID",
  "generated_at": "ISO 8601 timestamp",
  "source_snapshot_id": "string, FK -> EvidenceSnapshot",
  "pdf_uri": "string, storage location of the generated PDF"
}
```

**Content is restricted to the customer's own transaction and device facts** — amount, date/time,
payment rail, the customer's own device/login facts (e.g. "login from an unrecognised device"),
and the disputed transaction's details. It explicitly **excludes** any indicator that exposes
other people's data or the bank's internal risk signals: `IND-BENEFICIARY-LINKED` (reveals the
beneficiary appeared in other customers' cases), `IND-SAFPS-GRID-HIT` (reveals an industry-level
fraud-intelligence signal about the beneficiary), and any entity-graph link (§7) are never
included in this export, even though they may appear in the investigator-facing narrative. Every
included claim still cites an evidence ID (same discipline as the narrative validator in §10 — no
uncited claim, no verdict). This is distinct from an STR: it summarises the customer's own
transaction/dispute using only their own data, not an internal suspicious-activity determination,
so it does not trigger the FICA tipping-off isolation that gates `START_STR` (`BRS.md` §6) —
confirm with compliance/legal before implementation, since the distinction is a legal one, not
just a technical one.

## 7. Entity Graph Model

### 7.1 Nodes and edges

| # | Node type | Key | Edge types out |
|---|-----------|-----|-----------------|
| 1 | Customer | `customer_id` | `USES_DEVICE`, `OWNS_ACCOUNT` |
| 2 | Account | `account_id` | `OWNED_BY`, `PAID` |
| 3 | Device | `device_fingerprint` | `USED_BY` |
| 4 | Phone | `phone_number` | `USED_BY` |
| 5 | IP | `ip_address` | `USED_FROM` |

Modelled as a generic labelled-property graph (node type, key, edge type, edge properties
`{first_seen, last_seen}`) so the same query shape (`n`-hop traversal from a starting node,
filtered by edge type) runs unchanged against a local graph library in Phase 3 and against Amazon
Neptune in Phase 4 — only the driver changes.

### 7.2 GraphLink schema (as surfaced on a case)

```json
{
  "linked_entity_type": "enum: CUSTOMER | ACCOUNT | DEVICE | PHONE | IP",
  "linked_entity_id": "string",
  "shared_attribute": "enum: DEVICE | PHONE | IP | ACCOUNT",
  "hops": "int, 1 or 2",
  "narrative_hint": "string, e.g. 'This device was used by 2 other customers who each paid known mules'"
}
```

### 7.3 Query

1-hop: entities directly sharing a device/phone/IP/account with this case's customer or
beneficiary. 2-hop: entities connected via one intermediate shared attribute. Only links where the
intermediate/target node has `prior_case_count >= 1` are surfaced, to keep the graph view relevant
rather than exhaustive.

## 8. Scenario Classifier

Deterministic, rule-based on the computed indicators/counter-indicators (not a separate ML
model — consistent with BRS §4.1 item 5). Output is always phrased as **"consistent with"** a
scenario, never an assertion — the case schema's `scenario_evidence` field (§6) names exactly
which rule(s) produced the label, so the investigator can see and challenge the basis for it, not
just the conclusion.

| # | Scenario | Fires when | `scenario_evidence` |
|---|----------|-----------|----------------------|
| 1 | `MULE` | `IND-RAPID-PASSTHROUGH` fired — the alert's own customer received a large inbound deposit shortly before sending this transfer out. This is the actual mule signal (the customer's account is the pass-through), distinct from paying a known-bad beneficiary (rule 3 below). Evaluated first, since it is the most specific pattern and the least likely to false-positive against the others. | `['IND-RAPID-PASSTHROUGH']` |
| 2 | `ACCOUNT_TAKEOVER` | `IND-DEVICE-UNUSUAL` or `IND-RECENT-SIM-SWAP` fired, and `CI-DEVICE-USUAL` did not | `['IND-DEVICE-UNUSUAL']` and/or `['IND-RECENT-SIM-SWAP']` |
| 3 | `APP_SCAM` | Device/location counter-indicators hold (`CI-DEVICE-USUAL`, `CI-NO-CREDENTIAL-CHANGE` both fired) but `IND-BENEFICIARY-NEW` and `IND-AMOUNT-HIGH` fired | `['IND-BENEFICIARY-NEW', 'IND-AMOUNT-HIGH']` |
| 4 | `FIRST_PARTY` | `CI-CUSTOMER-TENURE` fired, no device/beneficiary indicators fired, but `IND-AMOUNT-HIGH` fired — phrased on the case screen as "consistent with first-party fraud," never as an accusation; long tenure plus one high-amount indicator is weak, single-signal evidence and must be presented as exactly that | `['IND-AMOUNT-HIGH', 'CI-CUSTOMER-TENURE']` |
| 5 | `UNCLASSIFIED` | None of the above patterns match | `[]` |

Note: `IND-BENEFICIARY-LINKED` (the beneficiary itself appeared in prior cases) is surfaced to the
investigator as an indicator either way (§5.2 #3) but no longer drives `MULE` classification — it
flags a suspect *destination* account, which is a different fact from the *customer's own account*
being used as a pass-through.

Evaluated top-to-bottom; first match wins. Classification result is stored on the case and drives
the "likely scenario" line on the case screen (HLD.md §5) and which action is emphasised (e.g.
`APP_SCAM` emphasises "Contact customer").

## 9. LLM Narrative — Exact Prompt

**The original version of this prompt passed the raw `payment_reference`/`beneficiary_name` free
text to the model and told it to describe instruction-like content without citing it — but the
validator (§10) rejects any sentence without a citation, so a prompt-injection demo case could
never produce a validatable narrative; the safety mechanism and the validator directly
contradicted each other.** Fixed by removing raw free text from the prompt entirely.
`IND-INJECTION-LIKE-TEXT` (§5.2 #12) detects instruction-like content in `payment_reference`/
`beneficiary_name` **deterministically, before the LLM is ever called**, and turns it into an
indicator with its own evidence ID like any other fact. The LLM never sees the raw free text at
all — only the indicator's already-sanitised statement — so every sentence it could write about
that content already has something citable.

```text
SYSTEM:
You write a factual narrative for a bank fraud investigator. You are given a
fixed list of computed indicators and counter-indicators, each with an
evidence ID. Rules, all mandatory:
1. Every sentence you write must end with one or more evidence ID citations
   in square brackets, e.g. [E1] or [E1][E2].
2. Every number you state must appear verbatim in the supplied indicators.
   Do not compute, round, or estimate any new number.
3. You must never state a verdict, a risk score, a probability, or any
   phrase implying a conclusion such as "likely fraud" or "safe to release."
4. You must include counter-indicators in the narrative, not only
   indicators.
5. Only use the indicators and counter-indicators listed below. You have no
   other source of information about this case.
6. Do not use any tool. You have none available.
7. Output plain text only, no markdown, no headers.

USER:
Case scenario: consistent with {likely_scenario}

Indicators:
{for each indicator: "- [{evidence_ids}] {statement} (severity: {severity})"}

Counter-indicators:
{for each counter_indicator: "- [{evidence_ids}] {statement}"}

Write a narrative of no more than 6 sentences summarising this case for the
investigator, following all rules above.
```

Because the model receives no raw customer-controlled text at all — only deterministic,
pre-computed indicator statements — there is no remaining channel for injected instructions to
reach the model. The `IND-INJECTION-LIKE-TEXT` demo case now exercises this end to end: the
deterministic rule fires, its statement (e.g. "the payment reference contains text resembling an
instruction [E-txn]") enters the indicator list like any other fact, the model cites it normally,
and the validator passes it normally — no special-casing required.

Model is invoked read-only (no tool/function-calling definitions attached), in an approved
in-region deployment, with no fine-tuning/training on the input data (BRS §6).

## 10. Citation & Number Validator

### 10.1 Algorithm

1. Split the narrative into sentences.
2. For each sentence, extract citation tags matching `\[E\d+\]`. Reject the narrative if any
   sentence has zero citations.
3. For each citation tag, confirm the evidence ID exists in this case's indicator/counter-indicator
   list. Reject if any citation references an unknown ID.
4. Extract every numeric token from the narrative (amounts, multipliers, counts, durations),
   **excluding digits inside `[E\d+]` citation tags themselves** — the `1` in `[E1]` is a citation
   index, not a claimed fact, and must never be checked against evidence statements.
5. **Normalise both the extracted narrative numbers and the evidence statement numbers to a common
   form before comparing** (strip currency symbols and thousands separators, e.g. `R85,000` and
   `85000` must compare equal; normalise multipliers like `10.6x` and `10.6 times` the same way).
   Confirm each normalised number appears in the normalised `statement` text of at least one
   indicator/counter-indicator cited in that sentence. Reject on any mismatch.
6. Confirm the narrative contains no verdict/score vocabulary from a maintained banned-phrase list
   (e.g. "likely fraud," "risk score," "recommend blocking"). Reject on a match.
7. **Best-effort directional-consistency check**: for each cited sentence, if the source
   indicator's `statement` contains a directional/comparative word (e.g. "above," "below," "more
   than," "fewer than," "before," "after"), confirm the narrative sentence does not use an opposite
   directional word for the same cited fact. Reject on a clear mismatch.
8. If any step rejects, set `case.narrative = null`, `case.narrative_status = UNAVAILABLE`, and the
   case ships with the reason logged in the audit record (US-E.2).

### 10.1a Known, unsolved limitations

This validator checks **citation existence and number accuracy** — it does not, and cannot fully,
verify semantic correctness. Documented residual risks, not claimed as closed:

- Step 7's directional check is a keyword heuristic, not a semantic parse — a sentence that
  reverses meaning without using a caught keyword pair can still pass (e.g. rephrasing "above" as
  a synonym not in the checked word list).
- The banned-phrase list (step 6) is a fixed list and can be paraphrased around (e.g. "warrants
  immediate blocking" instead of "recommend blocking"). Treat it as a coarse filter, not a
  guarantee that no verdict-like language ever ships.
- Mitigation for both is defense-in-depth, not closure: the known-outcome case injection
  (design §3.6, US-E.4) exists specifically to keep investigators reading narratives critically
  rather than trusting the validator to catch every subtle drift, and any investigator-flagged bad
  narrative should feed back into expanding the banned-phrase list and directional-word list over
  time.

### 10.2 Validation result schema

```json
{
  "case_id": "string",
  "result": "enum: PASS | FAIL",
  "failed_rule": "string | null, e.g. 'uncited_sentence' | 'unknown_citation' | 'number_mismatch' | 'banned_phrase' | 'directional_mismatch'",
  "narrative_checked": "string",
  "validated_at": "ISO 8601 timestamp"
}
```

## 11. Audit Record Schema

```json
{
  "case_id": "string",
  "snapshot_hash": "string, FK -> EvidenceSnapshot.content_hash of case.latest_snapshot_id at decided_at time -- fixes which of the case's (possibly several) snapshot versions this decision was based on",
  "model_version": "string",
  "prompt_version": "string",
  "narrative": "string | null",
  "validation_result": "ValidationResult",
  "evidence_views": ["{evidence_id, investigator_id, viewed_at}"],
  "decision": "enum: CONTACT_CUSTOMER | RELEASE | BLOCK | ESCALATE | REQUEST_INFO | START_STR",
  "reason_code": "string, mandatory, from a controlled list",
  "rationale": "string, mandatory free text",
  "decided_by": "string, investigator ID",
  "decided_at": "ISO 8601 timestamp"
}
```

Append-only: no update/delete operation exists on this table (US-F.2).

## 12. Outcome Schema

```json
{
  "case_id": "string",
  "outcome": "enum: CONFIRMED_FRAUD | CONFIRMED_LEGITIMATE | CUSTOMER_DISPUTE | RECOVERED | LAW_ENFORCEMENT_REQUEST | UNKNOWN",
  "recorded_by": "string, authorised reviewer ID",
  "recorded_at": "ISO 8601 timestamp",
  "notes": "string"
}
```

Write access restricted to an `authorised_reviewer` role (US-G.1) to prevent label poisoning of
the feedback loop.

## 13. Step Functions State Machine

The original version of this state machine had every `DeduplicateAndMerge` outcome fall through
into `GatherEvidence` unconditionally — a genuine duplicate would still trigger a full evidence
gather for nothing. Fixed with a `Choice` state reading `dedup-merge`'s classification
(`NEW_CASE` / `DUPLICATE` / `MERGED`) and branching accordingly. Evidence-source states no longer
retry on timeout (a retried timeout would silently double the §3 schema's advertised `timeout_ms`,
which defeats the point of an explicit, bounded timeout), and the `*Failed` states now construct an
actual `EvidenceSourceResult` object (§3) via `Parameters` instead of an empty `Pass`.

```json
{
  "Comment": "Fraud Investigation Copilot - case build pipeline",
  "StartAt": "DeduplicateAndMerge",
  "States": {
    "DeduplicateAndMerge": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:function:dedup-merge",
      "ResultPath": "$.dedupResult",
      "Next": "RouteOnDedupResult",
      "Catch": [{"ErrorEquals": ["States.ALL"], "Next": "CaseCreationFailed"}]
    },
    "RouteOnDedupResult": {
      "Type": "Choice",
      "Choices": [
        {"Variable": "$.dedupResult.classification", "StringEquals": "DUPLICATE", "Next": "LogDuplicateAndStop"},
        {"Variable": "$.dedupResult.classification", "StringEquals": "MERGED", "Next": "GatherEvidence"},
        {"Variable": "$.dedupResult.classification", "StringEquals": "NEW_CASE", "Next": "GatherEvidence"}
      ],
      "Default": "CaseCreationFailed"
    },
    "LogDuplicateAndStop": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:duplicate-logger",
      "End": true
    },
    "GatherEvidence": {
      "Type": "Parallel",
      "Branches": [
        {"StartAt": "FetchCustomer", "States": {"FetchCustomer": {
          "Type": "Task", "Resource": "arn:aws:lambda:...:function:evidence-customer",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "CustomerFailed"}],
          "End": true},
          "CustomerFailed": {"Type": "Pass",
            "Parameters": {"source": "CUSTOMER", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchTransaction", "States": {"FetchTransaction": {
          "Type": "Task", "Resource": "arn:aws:lambda:...:function:evidence-transaction",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "TransactionFailed"}],
          "End": true},
          "TransactionFailed": {"Type": "Pass",
            "Parameters": {"source": "TRANSACTION", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchBeneficiary", "States": {"FetchBeneficiary": {
          "Type": "Task", "Resource": "arn:aws:lambda:...:function:evidence-beneficiary",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "BeneficiaryFailed"}],
          "End": true},
          "BeneficiaryFailed": {"Type": "Pass",
            "Parameters": {"source": "BENEFICIARY", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchDevice", "States": {"FetchDevice": {
          "Type": "Task", "Resource": "arn:aws:lambda:...:function:evidence-device",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "DeviceFailed"}],
          "End": true},
          "DeviceFailed": {"Type": "Pass",
            "Parameters": {"source": "DEVICE", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchKYC", "States": {"FetchKYC": {
          "Type": "Task", "Resource": "arn:aws:lambda:...:function:evidence-kyc",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "KYCFailed"}],
          "End": true},
          "KYCFailed": {"Type": "Pass",
            "Parameters": {"source": "KYC", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}},
        {"StartAt": "FetchSAFPS", "States": {"FetchSAFPS": {
          "Type": "Task", "Resource": "arn:aws:lambda:...:function:evidence-safps",
          "TimeoutSeconds": 2,
          "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error", "Next": "SAFPSFailed"}],
          "End": true},
          "SAFPSFailed": {"Type": "Pass",
            "Parameters": {"source": "SAFPS", "status": "FAILED", "evidence_id.$": "$.evidenceId", "error.$": "$.error"},
            "End": true}}}
      ],
      "Next": "FreezeSnapshot"
    },
    "FreezeSnapshot": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:snapshot-writer",
      "Comment": "Appends a new immutable EvidenceSnapshot to case.snapshot_ids (sec 6) and sets latest_snapshot_id -- never mutates a prior snapshot, including on the MERGED path",
      "Next": "ComputeIndicators"
    },
    "ComputeIndicators": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:indicator-engine",
      "Next": "ResolveEntityGraph"
    },
    "ResolveEntityGraph": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:entity-graph",
      "Next": "ClassifyScenario"
    },
    "ClassifyScenario": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:scenario-classifier",
      "Next": "GenerateNarrative"
    },
    "GenerateNarrative": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:llm-narrative",
      "TimeoutSeconds": 10,
      "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.narrativeError", "Next": "ValidateNarrative"}],
      "Next": "ValidateNarrative"
    },
    "ValidateNarrative": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:narrative-validator",
      "Next": "PrioritiseAndStoreCase"
    },
    "PrioritiseAndStoreCase": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:case-writer",
      "End": true
    },
    "CaseCreationFailed": {
      "Type": "Task", "Resource": "arn:aws:lambda:...:function:alert-dlq-writer",
      "End": true
    }
  }
}
```

`GenerateNarrative` failing or timing out routes into `ValidateNarrative` regardless (with the
error captured), which treats a missing narrative the same as a failed validation — the case still
reaches `PrioritiseAndStoreCase` with `narrative_status = UNAVAILABLE` (US-E.2, design §3.14).

A timeout on any evidence branch now goes straight to that branch's `*Failed` Pass state — no
retry — since a retried timeout would exceed the timeout the schema advertises to the rest of the
system as this source's maximum wait.

## 14. Traceability Summary

| # | LLD section | User story |
|---|-------------|-----------|
| 1 | §2 Alert schema | US-A.1, US-A.2, US-A.3 |
| 2 | §3 Evidence source result | US-B.1, US-B.2 |
| 3 | §4 Evidence snapshot | US-C.1 |
| 4 | §5 Indicator engine | US-C.2, US-C.3 |
| 5 | §7 Entity graph | US-D.1 |
| 6 | §8 Scenario classifier | US-D.2 |
| 7 | §9-10 Prompt & validator | US-E.1, US-E.2, US-E.3, US-E.4 |
| 8 | §11 Audit record | US-F.1, US-F.2 |
| 9 | §12 Outcome schema | US-G.1 |
| 10 | §13 State machine | US-H.1 |
| 11 | §3.1 SAFPS evidence source | US-B.4 |
| 12 | §6.1 SAPS evidence PDF | US-F.3 |
