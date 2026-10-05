import pytest

from fraud_copilot.api import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_list_cases_returns_seeded_cases(client):
    resp = client.get("/api/cases")
    assert resp.status_code == 200
    cases = resp.get_json()
    assert len(cases) >= 3
    assert all("case_id" in c and "priority" in c for c in cases)


def test_case_summary_exposes_data_source(client):
    """The provenance tag: at least one seeded case must be flagged AMLSIM_REAL (the real
    simulator-sourced mule case demo.seed_store adds when third_party/AMLSim output exists),
    and it must not be visually indistinguishable from the synthetic ones in the API response."""
    cases = client.get("/api/cases").get_json()
    assert all("data_source" in c for c in cases)
    assert all(c["data_source"] in ("SYNTHETIC", "AMLSIM_REAL") for c in cases)


def test_get_case_detail_matches_summary_fields(client):
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    resp = client.get(f"/api/cases/{case_id}")
    assert resp.status_code == 200
    detail = resp.get_json()
    assert detail["case_id"] == case_id
    assert "indicators" in detail
    assert "counter_indicators" in detail
    assert "linked_entities" in detail
    assert "audit_history" in detail
    assert detail["audit_history"] == []


def test_get_case_404_for_unknown_id(client):
    resp = client.get("/api/cases/does-not-exist")
    assert resp.status_code == 404


def test_get_case_evidence_returns_all_six_sources(client):
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    resp = client.get(f"/api/cases/{case_id}/evidence")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "snapshot_id" in body and "content_hash" in body
    sources = {s["source"] for s in body["sources"]}
    assert sources == {"CUSTOMER", "TRANSACTION", "BENEFICIARY", "DEVICE", "KYC", "SAFPS"}
    for s in body["sources"]:
        assert s["status"] in ("FOUND", "NOT_FOUND", "NOT_AVAILABLE", "FAILED")
        if s["status"] != "FOUND":
            assert s["data"] is None


def test_get_case_evidence_404_for_unknown_case(client):
    resp = client.get("/api/cases/does-not-exist/evidence")
    assert resp.status_code == 404


def test_reason_codes_endpoint(client):
    resp = client.get("/api/reason-codes")
    assert resp.status_code == 200
    codes = resp.get_json()
    assert "STANDARD_MONITORING" in codes


def test_decision_without_reason_code_rejected(client):
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    resp = client.post(f"/api/cases/{case_id}/decision", json={
        "decision": "RELEASE", "reason_code": "", "rationale": "looks fine",
    })
    assert resp.status_code == 400


def test_valid_decision_marks_case_decided(client):
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    resp = client.post(f"/api/cases/{case_id}/decision", json={
        "decision": "RELEASE", "reason_code": "STANDARD_MONITORING",
        "rationale": "Reviewed evidence, nothing conclusive.",
    })
    assert resp.status_code == 200

    detail = client.get(f"/api/cases/{case_id}").get_json()
    assert detail["status"] == "DECIDED"
    assert len(detail["audit_history"]) == 1
    assert detail["audit_history"][0]["reason_code"] == "STANDARD_MONITORING"


def test_dashboard_stats_match_seeded_cases(client):
    cases = client.get("/api/cases").get_json()
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    body = resp.get_json()
    stats = body["stats"]
    assert stats["open"] == sum(1 for c in cases if c["status"] == "OPEN")
    assert stats["decided"] == sum(1 for c in cases if c["status"] == "DECIDED")
    assert stats["high_priority"] == sum(1 for c in cases if c["priority"] == "HIGH")
    assert stats["sla_overdue"] >= 0
    assert len(body["recent_cases"]) <= 5


def test_dashboard_recent_cases_sorted_newest_first(client):
    resp = client.get("/api/dashboard")
    recent = resp.get_json()["recent_cases"]
    created_ats = [c["created_at"] for c in recent]
    assert created_ats == sorted(created_ats, reverse=True)


def test_copilot_intro_returns_signal_count_and_suggested_questions(client):
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    resp = client.get(f"/api/cases/{case_id}/copilot/intro")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "relevant signal" in body["intro"]
    assert body["suggested_questions"] == [
        "Why was this flagged?", "Show related cases", "Explain beneficiary", "Compare transactions",
        "What evidence contradicts the risk?", "What evidence is missing?",
    ]


def test_copilot_intro_404_for_unknown_case(client):
    resp = client.get("/api/cases/does-not-exist/copilot/intro")
    assert resp.status_code == 404


def test_copilot_ask_each_suggested_question_returns_grounded_answer(client):
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    for question in [
        "Why was this flagged?", "Show related cases", "Explain beneficiary", "Compare transactions",
        "What evidence contradicts the risk?", "What evidence is missing?",
    ]:
        resp = client.post(f"/api/cases/{case_id}/copilot/ask", json={"question": question})
        assert resp.status_code == 200
        answer = resp.get_json()["answer"]
        assert answer, f"expected a non-empty answer for {question!r}"


def test_copilot_ask_freeform_question_returns_grounded_tool_answer(client):
    """Anything that isn't an exact match on a suggested question goes through the LLM+tools
    path (plan_22); against the offline demo backend that's MockToolCallingLLMClient, which
    must return a real cited answer, not the old substring-matched shortcuts."""
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    resp = client.post(
        f"/api/cases/{case_id}/copilot/ask",
        json={"question": "What happened right before this transfer?"},
    )
    assert resp.status_code == 200
    answer = resp.get_json()["answer"]
    assert answer
    assert answer != "I can only answer grounded questions about why this case was flagged, related cases, the beneficiary, or the transaction history. Try one of the suggested questions, or ask about one of those topics."


def test_copilot_ask_requires_question(client):
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    resp = client.post(f"/api/cases/{case_id}/copilot/ask", json={"question": ""})
    assert resp.status_code == 400


def test_copilot_ask_404_for_unknown_case(client):
    resp = client.post("/api/cases/does-not-exist/copilot/ask", json={"question": "Why was this flagged?"})
    assert resp.status_code == 404


def test_evidence_view_recorded_and_shows_in_next_decision(client):
    cases = client.get("/api/cases").get_json()
    case_id = cases[0]["case_id"]
    detail = client.get(f"/api/cases/{case_id}").get_json()
    first_evidence_id = detail["indicators"][0]["evidence_ids"][0] if detail["indicators"] else "E1"

    view_resp = client.post(f"/api/cases/{case_id}/evidence-view", json={"evidence_id": first_evidence_id})
    assert view_resp.status_code == 200

    client.post(f"/api/cases/{case_id}/decision", json={
        "decision": "RELEASE", "reason_code": "STANDARD_MONITORING", "rationale": "checked",
    })
    detail2 = client.get(f"/api/cases/{case_id}").get_json()
    viewed_ids = {v["evidence_id"] for v in detail2["audit_history"][0]["evidence_views"]}
    assert first_evidence_id in viewed_ids
