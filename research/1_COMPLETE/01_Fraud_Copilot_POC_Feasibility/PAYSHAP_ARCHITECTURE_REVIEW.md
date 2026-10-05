# Review — PayShap/SAFPS-Specific Architecture vs. Current LLD

Assessing the pasted 4-module architecture (Ingestion → Contextual Enrichment → Generative Case
Synthesis → Next-Best-Action Dispatcher) against `docs/LLD.md` and the incumbent landscape from
`MARKET_NEED_ASSESSMENT.md`.

## 1. Bottom line

This architecture is **more locally differentiated** than the current LLD — it names real South
African rails and infrastructure (PayShap, ShapID, SAFPS) that none of the incumbents found in
market research (NICE Actimize, Quantexa, Lucinity, Verafin) appear to target specifically. Two
pieces are genuinely pitch-worthy additions. But one piece **regresses the design's core safety
claim**, and one piece **risks crossing the design's core "never decide/act" principle** if not
tightly scoped. Neither is a reason to reject the ideas — both are fixable by merging them into
the existing LLD's discipline rather than replacing it.

## 2. Module-by-module

### 2.1 Module 1 — Ingestion & Normalisation

Matches `LLD.md` §2 (Alert Schema) and the EventBridge/SQS intake in `HLD.md` §3. Naming
Actimize/SAS/Kafka as concrete upstream sources is a useful specificity upgrade — no conflict, no
regression. **Merge as-is**, using it to make the alert schema's `alert_reason`/source fields
concrete rather than generic.

### 2.2 Module 2 — Contextual Enrichment

- "Internal Telemetry Query" (90-day login footprint, device IDs, PayShap frequency) is a more
  specific version of the existing Customer + Device evidence sources (`LLD.md` §3.1). No
  conflict — **merge as a refinement**, not a new source.
- "External Intelligence Query" against the **SAFPS grid** is a genuine, concrete win. The current
  design explicitly reserves an empty slot for this (`fraud-investigation-copilot.md` §3.4: "design
  a slot for industry data sharing (for example, via SABRIC), even if it is empty at launch").
  SAFPS is a real, named, existing South African data-sharing body — this fills that slot with
  something concrete instead of a placeholder. **This is the single most pitch-worthy addition
  here.** It should become a sixth evidence source in `LLD.md` §3, with its own `FOUND / NOT_FOUND
  / NOT_AVAILABLE / FAILED` status like the other five — do not treat it as automatically
  authoritative; a SAFPS hit becomes an indicator with an evidence ID like any other source.

### 2.3 Module 3 — Generative Case Synthesis

- Fraud variant classification (Account Takeover vs. APP Scam) is a narrower version of
  `LLD.md` §8's four-way classifier (adds Mule, First-Party). Not a conflict — treat the pasted
  version as a simplified summary, keep the four-way classifier as the actual implementation.
- **Narrative generation is where this needs pushback.** "Transforms raw transaction codes and
  server logs into a 3-sentence plain English summary" says nothing about evidence citations, the
  validator, or the no-verdict rule. That citation-and-validator discipline (`LLD.md` §9-10) is
  the single most differentiated, safety-critical part of the current design relative to every
  incumbent found in research — it's specifically what stops the LLM from inventing facts
  (design §3.5) and what makes the output regulator-defensible (the exact Standard Bank
  inconsistency problem found in `PUBLIC_PAIN_SIGNALS.md` §2.1). **Do not adopt this module's
  narrative generation as described.** If merging this architecture, the narrative step must stay
  the existing cited, validated, no-verdict version — a plain 3-sentence summary with no citations
  is a regression, not a simplification.

### 2.4 Module 4 — Next-Best-Action Dispatcher

This is the highest-risk module and needs explicit scoping before it goes anywhere near a pitch or
a build.

- **Inter-bank recall/freeze message drafting** — as worded ("pre-populates an urgent inter-bank
  recall/freeze message targeting the receiving bank's fraud desk") it's ambiguous whether this is
  a draft for human review or something that gets dispatched automatically. The current design's
  core principle is explicit: *"code establishes the facts, AI explains them, the human decides"*
  (`fraud-investigation-copilot.md` §1), and §3.1 is explicit that immediate action stays with the
  bank's own rules, not the copilot. **This must be scoped as draft-only, requiring explicit human
  send** — same pattern as the existing `[CONTACT CUSTOMER]` action needing a mandatory reason
  code and rationale (`HLD.md` §5). If it auto-sends, it stops being an "intelligence layer" and
  becomes an acting system, which changes the entire risk, liability, and regulatory profile of
  the pitch.
- **SAPS evidence PDF for the customer** — this is genuinely novel and not offered, as far as this
  research found, by any of the incumbent copilots (Actimize FraudDESK, Quantexa Q Assist,
  Lucinity Luci, Verafin) — those are internal investigator tools, not customer-facing police-report
  packets. This is a real differentiation candidate for the pitch. One flag: the BRS's existing
  FICA tipping-off constraint (`BRS.md` §6) concerns STR drafting specifically, not a
  customer-facing evidence sheet about the customer's own dispute — those are legally distinct,
  but this should go past your compliance/legal contact before it's pitched as a feature, not
  assumed safe by analogy.

## 3. What to do with this

1. **Fold into the pitch as differentiation**: SAFPS grid integration (§2.2) and the SAPS evidence
   PDF (§2.4) are the two genuinely new, locally-grounded ideas that the generic incumbent
   landscape doesn't appear to cover — worth adding to `MARKET_NEED_ASSESSMENT.md` as the "why us,
   not NICE Actimize" angle.
2. **Do not fold in the plain narrative generation** (§2.3) — keep the existing cited/validated
   narrative; it's the design's actual safety differentiator and the public pain evidence found in
   `PUBLIC_PAIN_SIGNALS.md` shows exactly what happens without it.
3. **Gate the inter-bank recall draft as human-send-only** before it goes into any LLD revision or
   pitch — otherwise it contradicts the design's own stated core principle and turns a "code
   establishes facts, human decides" pitch into an acting-system pitch, which is a different,
   harder conversation with leadership (liability, regulatory exposure, a much bigger ask).
