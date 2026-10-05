# Fraud Investigation Copilot — Market Need Assessment (For Internal Pitch)

**Context**: You're a vendor/consultancy serving banks, considering pitching this to internal
leadership as a new product/initiative. No specific client pain point has been observed yet —
this assessment is based on external research, not an internal signal.

## 1. Short Answer

The underlying pain is real and growing. The specific product category you'd be pitching —
"AI copilot for fraud investigators with cited, evidence-linked narratives" — is **not** a gap in
the market. It's an active, well-funded category with multiple incumbents already selling this
exact capability to banks, including in South Africa.

## 2. The Problem Is Real

SABRIC's 2025 Annual Banking Crime Statistics Report:

| # | Metric | Value |
|---|--------|-------|
| 1 | Digital banking crime losses | R2.4bn (up from ~R1.9bn in 2024) |
| 2 | Banking-app fraud losses | R1.7bn (>70% of digital banking losses) |
| 3 | Reported incidents | 110,000+ |
| 4 | Primary driver | Social engineering / APP scams, not system compromise |

This matches the design's worked example almost exactly (a customer socially engineered into
authorising their own transfer) — the problem statement is verifiable and current.

## 3. The Product Category Is Already Served

| Vendor | Product | Overlap with this design |
|---|---|---|
| NICE Actimize | FraudDESK CoPilot (GenAI) | Alert triage, link analysis, case narration |
| Quantexa | Q Assist | Entity relationships, risk indicators, investigation narratives |
| Lucinity | Luci Copilot | Unified fraud/AML/sanctions case manager, narrative + evidence |
| Nasdaq Verafin | Entity Research Copilot | Multi-source consolidation into a source-backed narrative — close to this design's §3.5 validator concept |
| Feedzai | — | Links narrative generation to a structured, regulator-ready evidence package |

South African incumbent presence specifically:

- **Absa** (big-5 bank) runs FICO Falcon Fraud Manager with real-time customer verification —
  publicly cited 47% improvement in self-solve cases.
- **Aims** — local vendor, reportedly saved "a large South African bank" R300m+.
- **Clari5** — active in the SA market.
- **Scam Signal** — an industry-wide initiative (multiple banks + MTN Chenosis + FICO + Jersey
  Telecom + GSMA), live since October 2025, targeting this exact APP-scam problem at the network
  level.

## 4. Where an Actual Gap Might Exist

Enterprise suites (NICE Actimize, SAS) run **$1M+/year** in licensing and implementation — pricing
out smaller and challenger banks (mutual banks, neobanks like Bank Zero / TymeBank-tier players).
No incumbent found in this research dominates that tier with a **lean layer that sits on top of an
existing (dumb) fraud engine**, as opposed to a full detection-plus-case-management suite —
which is precisely how this design frames itself ("don't build another fraud detector, build the
intelligence layer for alerts the bank already generates").

That framing is the one plausible, defensible wedge: not competing head-on with NICE Actimize for
a big-5 bank's business, but serving banks priced out of the enterprise suites.

## 5. What This Means for the Pitch

| # | Point | Why it matters |
|---|-------|-----------------|
| 1 | Don't pitch it as novel | Leadership (or 10 minutes of diligence) will find the incumbent list in §3 immediately; an unqualified "no one's doing this" claim damages credibility |
| 2 | Pitch the segment, not the category | Mid-market/smaller SA banks priced out of enterprise suites — position as an add-on to existing bank relationships, not a head-on competitor to Actimize/Quantexa |
| 3 | The biggest hole right now | No observed client pain point exists yet — no fraud/ops contact has said "our investigators are drowning." A real client conversation is worth more to leadership than the design doc, however good it is |
| 4 | If an existing bank relationship exists | The credible ask is "let us prototype this as a value-add for an existing client," not "fund a new standalone product to compete with NICE Actimize" |

## 6. Recommended Next Step Before Pitching

Get one real conversation with an existing bank client's fraud or operations contact about their
current investigator workflow pain, before taking this to leadership. "Client X told us Y" is a
stronger opening than an unvalidated design document, no matter how well-specified.

## Sources

- [SABRIC 2025 Annual Banking Crime Statistics Report](https://banking.org.za/news/sabric-release-the-2025-annual-banking-crime-statistics-report/)
- [R2.4 billion stolen from South Africans](https://businesstech.co.za/news/banking/872115/r2-4-billion-stolen-from-south-africans-over-r21800-per-person/)
- [Banking apps become fraudsters' favourite weapon — R1.7bn](https://iol.co.za/business/2026-09-09-banking-apps-become-fraudsters-favourite-weapon-as-south-africans-lose-r17bn/)
- [FraudDESK CoPilot GenAI | NICE Actimize Xceed](https://www.niceactimize.com/xceed/frauddesk-copilot)
- [Internal Fraud Detection - Quantexa](https://www.quantexa.com/solutions/internal-fraud/)
- [How Absa improved fraud prevention using FICO tech](https://fintech.global/2026/04/27/how-absa-improved-fraud-prevention-using-fico-tech/)
- [South Africa Deploys Scam Signal](https://techafricanews.com/2026/02/05/south-africa-deploys-scam-signal-to-protect-consumers-against-rising-banking-fraud/)
- [NICE Actimize vs Feedzai](https://www.feedzai.com/blog/nice-actimize-vs-feedzai/)
