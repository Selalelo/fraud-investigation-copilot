import pytest

from fraud_copilot.outcomes import OutcomeStore, UnauthorisedReviewerError, decision_outcome_agreement_rate


def test_unauthorised_reviewer_rejected():
    store = OutcomeStore(authorised_reviewers={"reviewer1"})
    with pytest.raises(UnauthorisedReviewerError):
        store.record_outcome("CASE-1", "CONFIRMED_FRAUD", recorded_by="random_investigator")


def test_authorised_reviewer_can_record_outcome():
    store = OutcomeStore(authorised_reviewers={"reviewer1"})
    outcome = store.record_outcome("CASE-1", "CONFIRMED_FRAUD", recorded_by="reviewer1")
    assert outcome.case_id == "CASE-1"
    assert outcome.outcome == "CONFIRMED_FRAUD"


def test_invalid_outcome_value_rejected():
    store = OutcomeStore(authorised_reviewers={"reviewer1"})
    with pytest.raises(ValueError):
        store.record_outcome("CASE-1", "NOT_A_REAL_OUTCOME", recorded_by="reviewer1")


def test_agreement_rate_computed_correctly():
    store = OutcomeStore(authorised_reviewers={"reviewer1"})
    store.record_outcome("CASE-1", "CONFIRMED_FRAUD", recorded_by="reviewer1")
    store.record_outcome("CASE-2", "CONFIRMED_LEGITIMATE", recorded_by="reviewer1")
    decisions = {"CASE-1": "BLOCK", "CASE-2": "BLOCK"}  # one agrees, one doesn't
    rate = decision_outcome_agreement_rate(decisions, store.all_outcomes())
    assert rate == 0.5


def test_agreement_rate_none_when_nothing_to_compare():
    assert decision_outcome_agreement_rate({}, []) is None
