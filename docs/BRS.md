# 1. Business Requirements Specification — Fraud Investigation Copilot

Source design: `../fraud-investigation-copilot.md` (v2). Synthetic data only; no real bank data at
any phase.

## 2. Problem Statement

### 2.1 Scale of the problem

South Africa's 2025 SABRIC figures put digital banking crime losses at **R2.4 billion** and card
fraud losses at **R1.7 billion**. Both categories share the same operational bottleneck: a human
fraud investigator has to manually open 5–10 internal systems (customer profile, transaction
history, beneficiary history, device data, KYC) to decide whether a single flagged transaction is
fraud, and by the time that investigation finishes, real-time payment rails (RTC, PayShap) may
have already settled the money.

### 2.2 Why the existing fraud engine is not the fix

The bank's fraud engine already generates the alert. The gap is not detection — it is what
happens between the alert firing and a human making an informed, auditable decision. Loopholes in
a first attempt at closing this gap (v1) are catalogued in `../fraud-investigation-copilot.md`
§3, items 3.1–3.14, and each has a corresponding fix carried into this design.

## 3. Objective

> Build the intelligence layer that helps a human investigate the alerts the bank already
> generates. Do not build another fraud detector.

The copilot turns a raw alert into a complete, evidence-linked, auditable case, so an investigator
can decide quickly and correctly. It never makes or implies the final decision: **code establishes
the facts, AI explains them, the human decides, every step is recorded.**

## 4. Scope

### 4.1 In scope (MVP, per design §8)

| # | Item | Detail |
|---|------|--------|
| 1 | Alert type | Large transfer to a newly added beneficiary |
| 2 | Evidence sources | Customer, transactions, beneficiary, device, KYC (5 sources) |
| 3 | Data | Synthetic only — e.g. PaySim-style or IBM synthetic AML transaction datasets |
| 4 | Loop | Alert → case → investigator decision with mandatory reason code → audit log |
| 5 | AI role | Cited narrative generation and scenario classification only — no scoring, no verdict |
| 6 | Entity resolution | 1-2 hop entity graph links (device, phone, IP, account) |
| 7 | Infra | AWS reference architecture, expressed as Terraform, validated but not deployed to a live bank environment |

### 4.2 Out of scope

| # | Item | Reason |
|---|------|--------|
| 1 | New fraud-detection models | Explicitly rejected by the design's core principle (§1) |
| 2 | Automated hold/release/block execution | Bank's existing rules engine owns immediate action (§3.1); the copilot only informs the investigator's decision |
| 3 | STR (Suspicious Transaction Report) filing workflow | Kept in a separate, restricted workflow per §3.12, not built in this MVP |
| 4 | Cross-bank data sharing (e.g. SABRIC) integration | Design reserves a slot for it (§3.4) but ships empty at launch |
| 5 | Real customer/bank data of any kind | Constraint — see §6 |

## 5. Stakeholders

| # | Stakeholder | Interest |
|---|-------------|----------|
| 1 | Fraud investigator | Primary user of the case screen; needs fast, trustworthy, evidence-linked cases |
| 2 | Fraud operations management | Owns SLA/priority outcomes, wants consistency across investigators |
| 3 | Compliance / legal (POPIA, FICA) | Requires lawful data handling, tipping-off controls, auditability |
| 4 | Engineering / platform team | Builds and operates the pipeline, Lambdas, Step Functions, entity graph, LLM integration |
| 5 | Bank customer (indirect) | Subject of the evidence; protected by masking, least-privilege access, and the "contact customer" action rather than silent action |

## 6. Constraints

| # | Constraint | Source |
|---|------------|--------|
| 1 | POPIA — least-privilege access to personal data, fields masked unless the investigator needs them | Design §3.12 |
| 2 | FICA tipping-off — STR drafting kept isolated from customer communications | Design §3.12 |
| 3 | Synthetic data only, in-region/approved model, no training on bank data | Design §3.12, §8 |
| 4 | LLM is read-only and tool-less; never outputs a verdict, score, or fraud-likely label | Design §3.6, §3.7 |
| 5 | Every evidence source must report explicit status (FOUND / NOT_FOUND / NOT_AVAILABLE / FAILED) — silence must never be read as "clean" | Design §3.3 |
| 6 | Evidence is immutable once snapshotted (hashed, write-once) | Design §3.8 |

## 7. Success Metrics

Per design §7, the copilot is judged on investigator outcomes, not on "detecting fraud":

| # | Metric | What it measures |
|---|--------|-------------------|
| 1 | Time per case | From case opened to investigator decision |
| 2 | Consistency | Agreement of decisions across investigators on similar cases |
| 3 | Time to action | On held high-value payments, measured against the case's SLA timer |
| 4 | Narrative validation pass rate | How often the LLM narrative passes the citation/number validator; how often investigators flag a claim as wrong |
| 5 | Decision quality | Agreement between investigator decisions and confirmed outcomes (§3.13 feedback loop) |

## 8. Traceability

Every requirement in `USER_STORIES.md` traces to one or more of the 14 loophole fixes in
`../fraud-investigation-copilot.md` §3.1–3.14. Every schema and rule in `LLD.md` traces to a user
story here. This BRS is the root of that chain.
