"""LLM narrative generation (LLD.md sec 9, post design-review fix).

The prompt contains NO raw customer-controlled free text (payment_reference/beneficiary_name) --
only deterministic, pre-computed indicator/counter-indicator statements. This closes the original
design's validator deadlock: IND-INJECTION-LIKE-TEXT (indicators.py) detects instruction-like
content BEFORE this point and turns it into a normal cited indicator, so there is no remaining
channel for injected instructions to reach the model.
"""
from __future__ import annotations

import re
from typing import List, Protocol

from .models import Indicator, LikelyScenario

SYSTEM_PROMPT = """You write a factual narrative for a bank fraud investigator. You are given a
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
7. Output plain text only, no markdown, no headers."""

_PROMPT_LINE_RE = re.compile(r"^- ((?:\[[^\]]+\])+) (.+?)(?: \(severity: .+\))?$")


def build_prompt(
    likely_scenario: LikelyScenario, indicators: List[Indicator], counter_indicators: List[Indicator]
) -> str:
    lines = [f"Case scenario: consistent with {likely_scenario.value}", "", "Indicators:"]
    for i in indicators:
        cites = "".join(f"[{e}]" for e in i.evidence_ids)
        lines.append(f"- {cites} {i.statement} (severity: {i.severity.value if i.severity else 'n/a'})")
    lines += ["", "Counter-indicators:"]
    for i in counter_indicators:
        cites = "".join(f"[{e}]" for e in i.evidence_ids)
        lines.append(f"- {cites} {i.statement}")
    lines += [
        "",
        "Write a narrative of no more than 6 sentences summarising this case for the",
        "investigator, following all rules above.",
    ]
    return "\n".join(lines)


class LLMClient(Protocol):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        ...


class MockLLMClient:
    """Deterministic, offline stand-in for a real LLM. Parses the '- [Ex] statement (...)' lines
    straight out of the user prompt and writes one cited sentence per item, verbatim from the
    statement text -- so it always satisfies the citation and number rules by construction.
    Used so the pipeline/tests run with no external API dependency; swap in a real LLMClient
    (e.g. a Bedrock/Anthropic-backed one) to call an actual model against the same prompt."""

    MAX_SENTENCES = 6

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        items = []
        for line in user_prompt.splitlines():
            m = _PROMPT_LINE_RE.match(line.strip())
            if m:
                cites, statement = m.group(1), m.group(2)
                items.append((cites, statement))

        if not items:
            return ""

        sentences = [f"{statement} {cites}." for cites, statement in items[: self.MAX_SENTENCES]]
        return " ".join(sentences)


class BedrockLLMClient:
    """Real LLM client -- calls Amazon Bedrock (Claude, via an inference profile; on-demand
    direct model IDs aren't supported for these models in this account/region). Confirmed
    working with a live invoke-model call before being wired in here. The output still goes
    through validate() unmodified like the mock's does -- no special-casing for real-model
    output; if a completion doesn't cite properly, narrative_status correctly becomes
    UNAVAILABLE (design sec 3.14's fail-safe), which is the point of validating at all."""

    def __init__(
        self,
        model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        region: str = "us-east-1",
        max_tokens: int = 512,
    ):
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._model_id = model_id
        self._max_tokens = max_tokens

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        import json

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        })
        response = self._client.invoke_model(modelId=self._model_id, body=body)
        payload = json.loads(response["body"].read())
        return "".join(block.get("text", "") for block in payload.get("content", []))


def generate_narrative(
    likely_scenario: LikelyScenario,
    indicators: List[Indicator],
    counter_indicators: List[Indicator],
    llm_client: LLMClient = None,
) -> str:
    if llm_client is None:
        llm_client = MockLLMClient()
    if not indicators and not counter_indicators:
        return ""
    user_prompt = build_prompt(likely_scenario, indicators, counter_indicators)
    return llm_client.generate(SYSTEM_PROMPT, user_prompt)
