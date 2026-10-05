# 1. User Stories — Fraud Investigation Copilot

Grouped by epic. Every story is traced to the loophole(s) it fixes from
`../fraud-investigation-copilot.md` §3 (3.1–3.14). Story IDs: `US-<epic>.<n>`.

## 2. Epic A — Alert Intake & Deduplication

Fixes: §3.1 (money gone before investigation), §3.11 (duplicate alerts → duplicate cases).

### 2.1 US-A.1 — Idempotent alert intake

As the platform, I want every inbound alert to carry (or be assigned) an idempotency key, so that
EventBridge's at-least-once delivery never creates two cases for one alert.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | An alert with a previously-seen idempotency key is dropped, not reprocessed into a new case |
| 2 | The idempotency key is derived deterministically from alert fields when the source system doesn't supply one |
| 3 | A dropped duplicate is logged with a reference to the original case ID |

### 2.2 US-A.2 — Alert merging per customer/time window

As an investigator, I want alerts for the same customer within a short time window merged into
one case, so I don't work the same scam as three separate cases.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Two or more alerts for the same customer ID within the configured merge window are attached to a single case |
| 2 | Each merged alert is retained individually inside the case (not discarded) for audit purposes |
| 3 | The case's priority/SLA reflects the most urgent of its merged alerts |

### 2.3 US-A.3 — Immediate action stays with the bank, not the copilot

As compliance, I want the copilot to never issue hold/release/block instructions itself, so the
bank's existing rules engine remains the sole authority over immediate action.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | The alert intake schema records what immediate action the bank's rules engine already took (hold / step-up / delay / allow) as a fact, not a copilot decision |
| 2 | No pipeline component issues a payment-blocking instruction |

## 3. Epic B — Evidence Gathering

Fixes: §3.3 (missing data looks like clean data), §3.4 (only one side of the transaction visible), §3.12 (privacy/POPIA).

### 3.1 US-B.1 — Explicit evidence status per source

As an investigator, I want every evidence source to report FOUND, NOT_FOUND, NOT_AVAILABLE, or
FAILED explicitly, so I never mistake a timeout for a clean result.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Each of the six evidence sources (customer, transaction, beneficiary, device, KYC, SAFPS) always returns one of the four statuses, never a silent empty result |
| 2 | A source call has an explicit timeout; a timeout produces `FAILED` or `NOT_AVAILABLE`, not a hang |
| 3 | The case header surfaces an incompleteness warning whenever any source is not `FOUND` |

### 3.2 US-B.2 — External beneficiary labelling

As an investigator, I want beneficiaries at another bank labelled "external" with a clear
statement of what is and isn't knowable, so I don't misread "no history" as "clean."

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | A beneficiary account not owned by this bank is tagged `external` in the evidence record |
| 2 | The case screen states explicitly that external beneficiary history is unavailable rather than omitting it silently |
| 3 | A data-sharing slot (e.g. SABRIC-style) exists in the schema and returns `NOT_AVAILABLE` at launch without breaking the pipeline |

### 3.3 US-B.3 — Least-privilege, masked evidence

As compliance, I want evidence fields masked unless the investigator's action requires them, so
POPIA exposure is minimised.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | PII fields not needed for the current case view are masked by default |
| 2 | Unmasking an individual field is a tracked action (feeds the audit log, Epic F) |

### 3.4 US-B.4 — SAFPS grid check

As an investigator, I want the beneficiary account/ShapID checked against the SAFPS
(South African Fraud Prevention Service) grid, so an industry-known fraud target is surfaced
instead of looking clean just because it has no history inside this bank.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | The SAFPS check runs as a sixth evidence source, returning FOUND/NOT_FOUND/NOT_AVAILABLE/FAILED like every other source — never a silent skip |
| 2 | A grid match produces a HIGH-severity indicator with its own evidence ID; it does not itself set the case's priority or decide anything |
| 3 | Fills the industry data-sharing slot design §3.4 reserves as empty at launch, with a real named source |

## 4. Epic C — Indicators & Evidence Snapshot

Fixes: §3.5 (LLM can invent facts), §3.8 (evidence changes after the fact).

### 4.1 US-C.1 — Immutable evidence snapshot

As compliance, I want all gathered evidence frozen into hashed, write-once storage at case
creation, so I can prove months later exactly what the investigator saw.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Once a case's evidence is gathered, it is written to immutable storage and hashed |
| 2 | Any later re-fetch of the same evidence source does not alter the case's original snapshot |
| 3 | The case record stores the snapshot hash |

### 4.2 US-C.2 — Deterministic indicators and counter-indicators

As an investigator, I want every indicator and counter-indicator computed by deterministic code
with a cited evidence ID, so the facts on my screen are verifiable, not generated.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Each indicator rule takes the evidence snapshot as input and produces a fact + evidence ID, never free text |
| 2 | Counter-indicators are computed with the same rigor as indicators, not treated as an afterthought |
| 3 | The rule engine runs entirely on the frozen snapshot, never live data, so results are reproducible |

### 4.3 US-C.3 — Priority and SLA

As fraud operations management, I want every case assigned a priority and SLA timer, so a held
high-value transfer is worked before a low-value anomaly.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Priority is computed from amount, indicator severity, and immediate-action state (held payments rank above non-held) |
| 2 | The SLA timer starts at case creation and is visible on the case screen |
| 3 | Cases nearing or past SLA are flagged for escalation |

## 5. Epic D — Entity Graph & Scenario Classification

Fixes: §3.2 (assumes fraudster is the one transacting), §3.10 ("previous cases" as a search problem).

### 5.1 US-D.1 — 1-2 hop entity graph links

As an investigator, I want to see entities linked to this case by shared device, phone, IP, or
account within 1-2 hops, so I can spot "this device was used by 2 other customers who each paid
known mules" without manual cross-referencing.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | The graph resolves links up to 2 hops from the case's customer/beneficiary/device nodes |
| 2 | Graph queries run against the evidence snapshot's entities, modelled so the same query shape works against a graph database (Neptune) later |
| 3 | Each link surfaced on the case screen cites the shared attribute (device/phone/IP/account) that connects the entities |

### 5.2 US-D.2 — Likely-scenario classification

As an investigator, I want the case classified into a likely scenario (account takeover / APP
scam / mule / first-party fraud), so I know which evidence and actions are relevant before I start
reading.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | The classifier outputs exactly one of the four scenario labels (or "unclassified" if confidence is too low) from the computed indicators/counter-indicators |
| 2 | Classification is deterministic given the same evidence snapshot |
| 3 | Scenario label drives which actions are emphasised on the case screen (e.g. "Contact customer" for APP scam) |

## 6. Epic E — AI Narrative & Safety

Fixes: §3.5 (LLM invents facts), §3.6 (automation bias), §3.7 (prompt injection), §3.14 (no fallback).

### 6.1 US-E.1 — Cited-only narrative

As an investigator, I want the AI narrative to cite an evidence ID for every claim and never state
a verdict or score, so I read it as an explanation, not a recommendation.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | The LLM prompt supplies only computed indicators/counter-indicators (with evidence IDs) — never raw free text as instructions |
| 2 | The narrative contains no verdict, score, or "fraud likely" phrasing |
| 3 | Both indicators and counter-indicators appear in the narrative, not just the suspicious ones |

### 6.2 US-E.2 — Citation and number validator with safe fallback

As compliance, I want every narrative validated against the evidence store before it reaches an
investigator, and a graceful fallback when validation fails, so the queue never stalls and no
uncited claim ships.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Every sentence in the narrative must cite a valid evidence ID or the narrative is rejected |
| 2 | Every number in the narrative must match the evidence store or the narrative is rejected |
| 3 | On rejection, or on LLM/data-source unavailability, the case still ships with "AI narrative unavailable" and full raw evidence/indicators |

### 6.3 US-E.3 — Prompt injection resistance

As compliance, I want attacker-controlled free text (payment references, beneficiary names,
customer notes) kept out of the LLM prompt entirely, so a crafted reference like "ignore prior
instructions" has no channel to reach or steer the model.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Free-text fields (`payment_reference`, `beneficiary_name`) are never passed into the LLM prompt, in raw or quoted/escaped form — a deterministic rule (`IND-INJECTION-LIKE-TEXT`, LLD §5.2 #12) detects instruction-like content before the LLM is called and turns it into a cited indicator, which is all the LLM ever sees |
| 2 | The LLM has no tool access (read-only, tool-less) |
| 3 | A demo case with an injection payload in the payment reference produces a narrative that both cites the deterministic indicator and passes the citation/number validator (LLD §10) — the two mechanisms must not contradict each other |

### 6.4 US-E.4 — Automation-bias mitigation

As fraud operations management, I want counter-indicators always shown alongside indicators, and
periodic known-outcome cases inserted, so investigators keep genuinely reviewing instead of
rubber-stamping the AI.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | The case screen always renders a counter-indicators section, even when empty (shown as "none found") |
| 2 | The system can inject a known-outcome case into the queue for calibration purposes |

## 7. Epic F — Case Interface & Audit

Fixes: §3.9 (audit trail too thin), §3.12 (tipping-off).

### 7.1 US-F.1 — Case screen with mandatory reason code

As an investigator, I want a case screen showing priority, SLA, scenario, indicators,
counter-indicators, linked entities, and narrative, with actions gated by a mandatory reason code
and rationale, so every decision is deliberate and explained.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Actions available: Contact customer, Release, Block, Escalate, Request info, Start STR |
| 2 | No action commits without a reason code selected and free-text rationale entered |
| 3 | "Start STR" routes into an isolated workflow, separate from customer-communication actions (§3.12) |

### 7.2 US-F.2 — Append-only audit log

As compliance, I want an append-only audit record per case capturing the evidence snapshot hash,
model/prompt version, narrative and validation result, which evidence views the investigator
opened, and the final decision with reason code and rationale, so the case is regulator-ready.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | Audit entries are append-only — no update or delete path exists |
| 2 | Every evidence view by the investigator is recorded (view-tracking) |
| 3 | The audit record links to the immutable snapshot hash from US-C.1 |

### 7.3 US-F.3 — SAPS evidence PDF export

As an investigator, I want to generate a technical evidence PDF from a case's indicators for the
customer to take to SAPS, so the customer has a defensible, evidence-linked document without the
bank drafting an STR-adjacent communication.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | The PDF is investigator-triggered, never auto-generated or auto-sent |
| 2 | Every claim in the PDF cites an evidence ID, same discipline as the narrative validator (US-E.2) — no uncited claim, no verdict |
| 3 | Generating the PDF is logged to the audit trail (US-F.2), same as any other case action |
| 4 | This action is reviewed against the FICA tipping-off boundary (§3.12) before implementation — it summarises the customer's own dispute, not an internal suspicious-activity determination, but that distinction must be confirmed with compliance/legal, not assumed |

## 8. Epic G — Outcomes & Feedback Loop

Fixes: §3.13 (no learning loop).

### 8.1 US-G.1 — Outcome capture

As fraud operations management, I want the eventual confirmed outcome (customer dispute,
recovery, law enforcement request) captured against each case, so decision quality can be
measured against reality.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | An outcomes table links case ID → investigator decision → confirmed outcome, recorded whenever it becomes known |
| 2 | Only authorised reviewers can write/change outcome labels (prevents data poisoning) |
| 3 | Outcome data feeds the metrics in BRS.md §7 |

## 9. Epic H — AWS Infrastructure

Fixes: supports §3.1 (SLA/priority timeliness), §3.8 (immutable storage), §3.9 (audit), §3.12 (region/encryption).

### 9.1 US-H.1 — Terraform-defined reference architecture

As the platform team, I want the full AWS architecture (EventBridge, SQS, Step Functions,
Lambdas, DynamoDB, S3 Object Lock, Neptune, Bedrock IAM, CloudWatch, CloudTrail, KMS) defined in
Terraform with least-privilege IAM and encryption at rest, so the design in HLD.md/LLD.md is
deployable and auditable as code.

**Acceptance criteria**

| # | Criterion |
|---|-----------|
| 1 | `terraform validate` passes with no errors |
| 2 | Every IAM role/policy grants only the actions the corresponding component needs |
| 3 | S3 evidence storage uses Object Lock; DynamoDB and S3 use encryption at rest via KMS |
| 4 | No configuration permits bank data to be used for model training |
