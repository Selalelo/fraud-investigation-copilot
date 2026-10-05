# Public Pain Signals — Proxy for a Real Client Conversation

No direct client contact was available, so this substitutes public investigative journalism and
job-market evidence for a real conversation with a bank's fraud/ops team. Weaker than a real
conversation — still get one before pitching leadership (see `MARKET_NEED_ASSESSMENT.md` §6) —
but this is concrete and citable, not speculative.

## 1. What the job market confirms

South African bank fraud analyst/investigator roles (SA Glassdoor/Indeed/LinkedIn postings,
2026) consistently describe:

- Investigating and monitoring alert queues against defined rules, requiring the analyst to work
  "independently" under time pressure
- Investigating and evaluating narrative reports on suspicious activity "in strict accordance with
  processes and AML Law"
- Ensuring alerts are "actioned promptly to minimize loss"
- Required proficiency in named platforms (Falcon, Actimize) — confirming the deployed detection
  layer is exactly the "bank's fraud engine" this design assumes already exists and explicitly
  does not try to replace

This confirms the operational shape of the job (alert-driven, time-pressured, narrative-writing,
tool-dependent) but not a specific complaint about it being broken or overwhelming — no
Glassdoor/Indeed review text surfaced with that level of detail.

## 2. What investigative journalism confirms — the stronger signal

Two Daily Maverick pieces (2026-03) on real South African bank fraud disputes surface concrete,
named failure modes that map directly onto specific fixes in this design:

### 2.1 Inconsistent investigation output reaching the regulator

In a real, named case (Miranda Young vs. Standard Bank), the bank gave **three different
explanations across separate letters** about which card was used for a fraudulent withdrawal —
first her credit card, then her debit card, then an unrecognised card number — before reverting to
the credit card claim at the National Financial Ombud stage, with no explanation offered for the
contradiction.

**Maps directly to**: this design's immutable, hashed evidence snapshot (LLD §4) and append-only
audit record (LLD §11) — both exist specifically to make "what did the investigator actually see
and conclude" a fixed, provable fact instead of something that can shift between letters.

### 2.2 Evidence gaps treated as closed, not flagged

In a separate R2.3-million loss case, "no effort was ever made by the fraud department of Standard
Bank to check the client's electronic devices for the purposes of ascertaining whether the fraud
was due to any negligence on the part of the client" — i.e., a whole evidence category was simply
not gathered, with no visible flag that it was skipped.

**Maps directly to**: this design's explicit `FOUND / NOT_FOUND / NOT_AVAILABLE / FAILED` status
per evidence source (LLD §3.2) and the case-header incompleteness warning (design §3.3) — built
specifically so a skipped evidence source is visible on the case, not silently absent.

### 2.3 Slow, high-friction resolution from the customer's side

The Young case took roughly six months from discovery to ongoing ombud review; the customer
described "hours and hours...on the phone and sending emails, fighting with the bank."

**Relevant, but indirect**: this design targets investigator-side speed and SLA (design §7), not
customer-side dispute-resolution friction directly — the connection is plausible (faster, more
consistent initial investigation should reduce downstream dispute cycles) but not proven by this
source.

### 2.4 Regulator-level outcome imbalance

The National Financial Ombud's most recent report shows **banks prevail in 79% of complaints
versus customers in 21%** — the article notes this is consistent with either thorough
investigations or systemic bias, and does not resolve which.

**Relevant framing point for the pitch**: this statistic cuts both ways. It could support "banks
need more rigorous, defensible investigation" (this design's pitch) or undercut it ("banks already
win most disputes, so where's the urgency"). Don't lean on it uncritically — a leadership audience
capable of reading the ombud report themselves will see the ambiguity immediately.

### 2.5 What a working forensic investigator says the actual process looks like

Forensic investigator Craig Pedersen (quoted independently of any bank): "The first thing that the
bank will be considering is the element of 'how'... They're going to need some time to review
access logs and transactional history to see which medium was used to make the actual payment,"
and confirms audit logging already exists for changes like OTP delivery detail edits.

**Confirms**: the raw evidence (access logs, transaction history, credential-change logs) this
design's evidence sources model already exists inside banks — the gap this design targets is
*assembly and citation discipline*, not data availability.

## 3. What this evidence does and doesn't prove

| # | Claim | Supported? |
|---|-------|-----------|
| 1 | Real, named cases exist where SA bank fraud investigation output was inconsistent across communications to the customer/regulator | Yes — Young v. Standard Bank |
| 2 | Real, named cases exist where an evidence category was skipped without visible flagging | Yes — the R2.3m device-check case |
| 3 | Investigators are measurably overwhelmed (volume, backlog, headcount pressure) | **No** — not found in this research; would need a real internal conversation or leaked/reported operational metrics |
| 4 | Banks want to buy a tool to fix this specifically | **No** — not established; this is evidence the failure mode exists publicly, not evidence of banks' willingness to pay for a fix |
| 5 | The underlying raw evidence (logs, transaction history) already exists and is accessible | Yes, per an independent forensic investigator's account |

## 4. How to use this in the pitch

Use §2.1 and §2.2 as concrete, real-world illustrations of exactly the two loopholes this design
is built to close (§3.8/3.9 audit consistency, §3.3 evidence-status transparency) — they're more
persuasive than the design doc's own worked example because they're real, named, and already
public. Do **not** claim this proves banks will buy the product, or that investigators are
overwhelmed — those claims are unsupported by this research and would not survive scrutiny from
anyone who reads the same two articles.
