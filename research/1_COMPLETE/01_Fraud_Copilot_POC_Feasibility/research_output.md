# Fraud Investigation Copilot — Is It Worth Building? (POC Feasibility)

**Read time**: ~5 min. Sources: `docs/BRS.md`, `USER_STORIES.md`, `HLD.md`, `LLD.md`,
`fraud-investigation-copilot.md`. No external market research — this is a complexity/effort read
of the design you already have, not a business case.

## 1. Verdict

**Conditionally yes — but not as the 6-phase plan currently scopes it.**

The *idea* is genuinely good and well-specified: it correctly avoids the naive "AI detects fraud"
pitch, and the safety mechanisms (explicit evidence status, immutable snapshot, cited-only
narrative, mandatory validator, counter-indicators against automation bias) are real engineering,
not decoration. The docs you already have (BRS/US/HLD/LLD) are, on their own, a strong artifact —
numbered, traceable, internally consistent. That work is already banked regardless of what you
build next.

The problem is **Phase 4 (AWS/Terraform)**, which is the most expensive phase in the plan and adds
the least proof value. A proof of concept does not need to run on real AWS infrastructure to prove
the design works — it needs to run the pipeline end to end on synthetic data and show the 14
loophole fixes actually happening in code. Building 8+ real Terraform resources
(EventBridge/SQS/Step Functions/5 Lambdas/DynamoDB/S3 Object Lock/Neptune/Bedrock IAM/CloudWatch/
CloudTrail/KMS) to `terraform validate`-passing, least-privilege quality is realistically
multi-day-to-multi-week work, and actually deploying it costs real money (Neptune and NAT
gateways especially) for zero additional evidence that the *idea* holds up.

**Smallest genuine POC = Phase 1 + a cut-down Phase 2, no AWS, no web UI.** Roughly 1–3 focused
days, entirely local Python, zero cloud spend. See §4.

## 2. Effort vs. Proof Value by Phase

| # | Phase | Real time cost | Proof value | Verdict |
|---|-------|----------------|-------------|---------|
| 1 | 0 — Docs | Low (done) | High (traceable spec, already complete) | Keep — already paid for |
| 2 | 1 — Core pipeline (local) | Low-Medium (1-2 days: dataclasses, ~10 rules, JSON snapshot + sha256) | **Highest** — proves §3.1, 3.3, 3.4, 3.5, 3.8, 3.11 with pure code | Build — this is the POC's spine |
| 3 | 2 — AI layer & safety | Medium (prompt already exact in LLD §9; validator logic already specified in LLD §10) | High — proves §3.2, 3.5, 3.6, 3.7, 3.14, the most "novel" claims of the design | Build, but mock the LLM call (see §4) to avoid API dependency/cost blocking the demo |
| 4 | 3 — Entity graph & case UI | Graph: low (networkx, cheap). **Web UI: the real sink** — a styled case screen with actions, mandatory reason code, view-tracking is real frontend time | Graph: medium. Web UI: low incremental proof over a markdown/CLI rendering of the same case object | Build the graph; **replace the web UI with a formatted CLI/markdown case view** for the POC |
| 5 | 4 — AWS & Terraform | **Highest** — multi-day to multi-week for correct least-privilege IAM across 10 services, real cost to actually deploy (Neptune, NAT) | **Lowest** for POC purposes — LLD §13's state machine JSON already documents the AWS mapping without deploying it | **Defer indefinitely** unless the goal is specifically to demonstrate infra/Terraform skill, not to validate the product idea |
| 6 | 5 — Polish/demo video | Low, once a POC exists | Medium (communicates the work) | Do last, only after §4 exists |

## 3. Where the Real Time Cost Concentrates

1. **Terraform correctness at "least privilege" quality** (Phase 4) — IAM policy-per-Lambda,
   correct trust relationships, S3 Object Lock configuration, Neptune networking. This is
   specialist AWS work, not fraud-domain work, and it's the single biggest time sink in the plan
   relative to what it proves.
2. **A real, styled investigator web UI** (Phase 3) — case screen layout, action buttons, reason
   code dropdown, rationale field, view-tracking wiring. None of this is required to prove the
   *backend* claims (evidence status, snapshot immutability, indicator determinism, validator
   correctness) — a well-formatted terminal/markdown rendering of the same `Case` object proves
   the same logic for a fraction of the time.
3. **Getting the LLM narrative validator genuinely correct**, including the prompt-injection demo
   case — this is real, necessary work (it's the design's most distinctive safety claim), but it's
   bounded and already fully specified in `LLD.md` §9-10, so it's a translation task, not a design
   task.

## 4. Recommended Smallest POC (cut line)

Build, in order:

1. **Phase 1 as planned** — alert intake/dedup/merge, 5 mock evidence sources with explicit
   status, hashed write-once JSON snapshot, deterministic indicator/counter-indicator engine,
   case object with priority/SLA. *(This alone already demonstrates loopholes 3.1, 3.3, 3.4, 3.5,
   3.8, 3.11 — more than half the design's stated differentiators, in pure Python, no cloud.)*
2. **Cut-down Phase 2** — scenario classifier (rule-based, cheap); LLM narrative generation with a
   real LLM call *if you have API access handy*, otherwise a stubbed LLM function that returns a
   templated narrative so the validator still has real input to reject/accept against; the 4 demo
   cases (APP scam, likely legitimate, missing evidence, prompt injection) as fixtures; tests for
   the indicator engine, validator, and dedup.
3. **A markdown/CLI case renderer instead of Phase 3's web UI** — prints the case screen layout
   from `HLD.md` §5 to the terminal or a generated `.md` file per case, including actions as a
   menu and a simple in-memory append-only audit log. Skip the entity graph's Neptune-shape
   modelling unless you want it — a flat "linked cases via shared device/phone" lookup over the
   synthetic dataset proves the same point.
4. **Stop there for the "is this worth it" decision.** Write up what you built and decide *then*
   whether Phase 3's real UI, the full entity graph, and Phase 4's Terraform are worth the
   additional time — with a working POC in hand to judge that against, instead of judging it from
   the design doc alone.

This cut gets you a demoable, working proof of the design's actual claims in roughly 1-3 days
instead of the multi-week commitment the full 6-phase plan implies.

## 5. Honest Reasons This Might Not Be Worth Your Time

- **The docs alone may already be the valuable output**, depending on your goal. If the purpose is
  to demonstrate design thinking (portfolio, interview, spec-writing practice), you may already be
  done — building code adds marginal value only if you specifically want working software or plan
  to keep extending this.
- **No stated purpose was given for this build** (product exploration? portfolio piece? learning
  exercise? client pitch?), and that changes the right amount of investment enormously. A
  portfolio piece wants Phase 4's Terraform for the "I can do cloud" signal; a product-validation
  exercise doesn't need it at all. Worth deciding explicitly before continuing past the POC in §4.
- **The entity graph and full case UI are the parts most likely to balloon in scope** once started
  — "just add filtering," "just add auth," "just make it look nicer" — with no natural stopping
  point, unlike Phase 1's engine which has a fixed, already-specified rule set.
- **If the goal was ever "will this make money / get adopted by a real bank,"** that question is
  explicitly out of scope for both this design and this research — nothing here validates market
  demand, only that the design is internally coherent and buildable.

## 6. Bottom Line

Worth building the smallest POC in §4 — it's cheap (1-3 days), fully proves the design's real
claims, and costs nothing in cloud spend. **Not** worth committing to the full 6-phase plan,
especially Phase 4, until that POC exists and you've decided *why* you're building this beyond
"the design doc says to."
