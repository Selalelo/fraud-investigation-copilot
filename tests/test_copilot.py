from fraud_copilot import copilot, demo


def _sample_case_and_snapshot():
    store, _ = demo.build_store()
    case = store.all_cases()[0]
    snapshot = store.get_snapshot(case.latest_snapshot_id) if case.latest_snapshot_id else None
    return case, snapshot


def test_answer_exact_match_suggested_question_is_deterministic():
    case, snapshot = _sample_case_and_snapshot()
    result = copilot.answer("Why was this flagged?", case, snapshot)
    assert result and result != copilot._FALLBACK_ANSWER


def test_why_flagged_reads_as_natural_prose_with_real_numbers():
    case, snapshot = _sample_case_and_snapshot()
    result = copilot._why_flagged(case, snapshot)
    assert f"R{case.amount:,.0f}" in result
    assert "× higher than the customer's previous 12-month maximum" in result
    assert copilot._CITATION_RE.search(result) or "[E" in result


def test_answer_freeform_question_uses_mock_tool_client_by_default():
    case, snapshot = _sample_case_and_snapshot()
    result = copilot.answer("What happened right before this transfer?", case, snapshot, [])
    assert result and result != copilot._FALLBACK_ANSWER
    assert copilot._CITATION_RE.search(result)


class _UncitedLLMClient:
    """Simulates a real model that ignores the citation rules -- must fail closed."""

    def run(self, system_prompt, question, case, snapshot, audit_entries=None):
        return "This case looks like fraud, no citations needed."


class _BrokenLLMClient:
    """Simulates a client that raises (e.g. a real network/API failure) -- must fail closed."""

    def run(self, system_prompt, question, case, snapshot, audit_entries=None):
        raise RuntimeError("simulated Bedrock failure")


def test_answer_freeform_falls_back_when_llm_output_is_uncited():
    case, snapshot = _sample_case_and_snapshot()
    result = copilot.answer(
        "Tell me about this case.", case, snapshot, [], _UncitedLLMClient()
    )
    assert result == copilot._FALLBACK_ANSWER


def test_answer_freeform_falls_back_when_llm_client_raises():
    case, snapshot = _sample_case_and_snapshot()
    result = copilot.answer(
        "Tell me about this case.", case, snapshot, [], _BrokenLLMClient()
    )
    assert result == copilot._FALLBACK_ANSWER


def test_validate_tool_answer_rejects_unknown_citation():
    assert not copilot._validate_tool_answer(
        "The amount was R85,000 [TXN9].", {"TXN1": '{"data": {"current_amount": 85000.0}}'}
    )


def test_validate_tool_answer_rejects_number_not_in_cited_evidence():
    assert not copilot._validate_tool_answer(
        "The amount was R99,000 [TXN1].", {"TXN1": '{"data": {"current_amount": 85000.0}}'}
    )


def test_validate_tool_answer_accepts_grounded_citation():
    assert copilot._validate_tool_answer(
        "The amount was R85,000 [TXN1].", {"TXN1": '{"data": {"current_amount": 85000.0}}'}
    )


def test_get_device_evidence_tool_exposes_sim_swap_data():
    case, snapshot = _sample_case_and_snapshot()
    result = copilot._execute_tool("get_device_evidence", case, snapshot, [])
    assert result["status"] == "FOUND"
    assert "last_sim_swap_days" in result["data"]


def test_answer_freeform_sim_swap_question_is_grounded_not_fallback():
    case, snapshot = _sample_case_and_snapshot()
    result = copilot.answer("Was there a SIM swap?", case, snapshot, [])
    assert result and result != copilot._FALLBACK_ANSWER
    assert "[DEV1]" in result


def test_get_transaction_evidence_tool_exposes_payment_method():
    case, snapshot = _sample_case_and_snapshot()
    result = copilot._execute_tool("get_transaction_evidence", case, snapshot, [])
    data = result.get("data", result)
    assert data["payment_rail"] == case.payment_rail.value
    assert data["payment_reference"] == case.payment_reference
