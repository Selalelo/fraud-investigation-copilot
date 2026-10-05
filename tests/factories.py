"""Test helpers for building alerts and synthetic evidence worlds."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fraud_copilot.evidence_sources import (
    BeneficiaryRecord,
    CustomerRecord,
    DeviceRecord,
    KYCRecord,
    SAFPSRecord,
    SyntheticWorld,
    TransactionRecord,
)
from fraud_copilot.models import Alert, ImmediateAction, PaymentRail

NOW = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)


def make_alert(**overrides) -> Alert:
    defaults = dict(
        alert_id="ALERT-1",
        customer_id="CUST-1",
        transaction_id="TXN-1",
        amount=85000.0,
        beneficiary_id="BEN-1",
        beneficiary_bank="THIS_BANK",
        alert_reason="unusual_transaction",
        immediate_action=ImmediateAction.HOLD,
        alert_time=NOW,
        received_time=NOW,
        beneficiary_name="John Smith",
        payment_rail=PaymentRail.PAYSHAP,
        proxy_id="0821234567",
        payment_reference="rent",
    )
    defaults.update(overrides)
    return Alert(**defaults)


def clean_world() -> SyntheticWorld:
    """A world where every source resolves FOUND with no indicators firing and every
    counter-indicator condition holding -- a 'quiet' baseline for targeted tests."""
    return SyntheticWorld(
        customers={
            "CUST-1": CustomerRecord(
                tenure_years=5.0, kyc_tier="TIER_2", monthly_spend_min=500,
                monthly_spend_max=8000, prior_case_count=0,
            )
        },
        transactions={
            "CUST-1": TransactionRecord(history_12m_amounts=[1000, 2000, 3000, 5000]),
        },
        beneficiaries={
            "BEN-1": BeneficiaryRecord(
                account_age_days=400, external=False,
                date_added=NOW - timedelta(days=200), prior_case_count=0,
            )
        },
        devices={
            "CUST-1": DeviceRecord(
                device_fingerprint="fp-usual", is_usual_device=True, is_usual_location=True,
                last_sim_swap_days=None, last_password_reset_days=None,
                phone_number="0821234567", ip_address="102.10.10.1",
            )
        },
        kyc={"CUST-1": KYCRecord(verification_status="VERIFIED", last_updated=NOW - timedelta(days=100))},
        safps={"0821234567": SAFPSRecord(grid_match=False)},
    )
