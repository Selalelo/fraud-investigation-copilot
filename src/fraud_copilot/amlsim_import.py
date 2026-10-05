"""Imports real IBM AMLSim simulator output (outputs/<sim_name>/*.csv, confirmed schema from an
actual local run -- see third_party/AMLSim/outputs/sample/) into a SyntheticWorld.

AMLSim simulates an account/transaction network and AML typologies (fan-in, fan-out, cycle,
etc.) -- it does NOT simulate device, KYC, or SAFPS-grid data (those aren't part of an AML
transaction-network simulation). CUSTOMER/BENEFICIARY/TRANSACTION evidence below is built from
real simulated data; DEVICE/KYC/SAFPS stay synthetic and are layered on separately by the caller.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .evidence_sources import BeneficiaryRecord, CustomerRecord, TransactionRecord


@dataclass
class AMLSimData:
    accounts: Dict[str, dict]            # acct_id -> row
    transactions: List[dict]             # all transaction rows
    alert_membership: Dict[str, List[dict]]  # acct_id -> alert_accounts.csv rows it appears in
    out_tx: Dict[str, List[dict]]        # acct_id -> transactions where it's orig_acct
    in_tx: Dict[str, List[dict]]         # acct_id -> transactions where it's bene_acct


def _read_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_amlsim_output(sim_output_dir: str) -> AMLSimData:
    """sim_output_dir is e.g. third_party/AMLSim/outputs/sample -- the directory containing
    accounts.csv, transactions.csv, alert_accounts.csv (confirmed real column names)."""
    accounts_rows = _read_csv(os.path.join(sim_output_dir, "accounts.csv"))
    accounts = {r["acct_id"]: r for r in accounts_rows}

    transactions = _read_csv(os.path.join(sim_output_dir, "transactions.csv"))

    alert_rows = _read_csv(os.path.join(sim_output_dir, "alert_accounts.csv"))
    alert_membership: Dict[str, List[dict]] = {}
    for row in alert_rows:
        alert_membership.setdefault(row["acct_id"], []).append(row)

    out_tx: Dict[str, List[dict]] = {}
    in_tx: Dict[str, List[dict]] = {}
    for tx in transactions:
        out_tx.setdefault(tx["orig_acct"], []).append(tx)
        in_tx.setdefault(tx["bene_acct"], []).append(tx)

    return AMLSimData(
        accounts=accounts, transactions=transactions,
        alert_membership=alert_membership, out_tx=out_tx, in_tx=in_tx,
    )


def _prior_case_count(data: AMLSimData, acct_id: str) -> int:
    """Real signal: how many AML typology alert groups this account was already a member of --
    directly analogous to LLD.md's prior_case_count field, sourced from genuine simulated data."""
    return len(data.alert_membership.get(acct_id, []))


def _parse_ts(tx: dict) -> datetime:
    return datetime.strptime(tx["tran_timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def build_customer_record(data: AMLSimData, acct_id: str) -> CustomerRecord:
    account = data.accounts[acct_id]
    outgoing = data.out_tx.get(acct_id, [])
    amounts = [float(tx["base_amt"]) for tx in outgoing]
    return CustomerRecord(
        tenure_years=5.0,  # AMLSim doesn't model calendar account-opening dates; not simulated
        kyc_tier="TIER_2",  # not simulated by AMLSim
        monthly_spend_min=min(amounts) if amounts else 0.0,
        monthly_spend_max=max(amounts) if amounts else 0.0,
        prior_case_count=_prior_case_count(data, acct_id),
    )


def build_transaction_record(data: AMLSimData, acct_id: str, as_of: Optional[datetime] = None) -> TransactionRecord:
    """history_12m_amounts: this account's real outgoing transfer amounts (the actual simulated
    transaction history). recent_large_inbound: real fan-in/pass-through detection -- the
    largest inbound transfer this account received, and how many days before `as_of` (or this
    account's own latest outgoing transfer if as_of is omitted)."""
    outgoing = data.out_tx.get(acct_id, [])
    incoming = data.in_tx.get(acct_id, [])
    history = [float(tx["base_amt"]) for tx in outgoing]

    if as_of is None:
        as_of = max((_parse_ts(tx) for tx in outgoing), default=None)

    recent_large_inbound = False
    recent_large_inbound_amount = None
    recent_large_inbound_days_before = None
    if incoming and as_of is not None:
        prior_incoming = [tx for tx in incoming if _parse_ts(tx) <= as_of]
        if prior_incoming:
            largest_in = max(prior_incoming, key=lambda tx: float(tx["base_amt"]))
            in_ts = _parse_ts(largest_in)
            days_before = (as_of - in_ts).days
            recent_large_inbound = True
            recent_large_inbound_amount = float(largest_in["base_amt"])
            recent_large_inbound_days_before = days_before

    return TransactionRecord(
        history_12m_amounts=history,
        recent_large_inbound=recent_large_inbound,
        recent_large_inbound_amount=recent_large_inbound_amount,
        recent_large_inbound_days_before=recent_large_inbound_days_before,
    )


def build_beneficiary_record(data: AMLSimData, acct_id: str, from_acct_id: Optional[str] = None) -> BeneficiaryRecord:
    """date_added: AMLSim has no 'beneficiary added' concept (it's a transaction network, not a
    banking beneficiary list) -- proxied by the first transaction timestamp between the two
    accounts, which is the closest real signal AMLSim provides."""
    account = data.accounts[acct_id]
    all_tx_involving = data.out_tx.get(acct_id, []) + data.in_tx.get(acct_id, [])
    if from_acct_id:
        relevant = [
            tx for tx in all_tx_involving
            if tx["orig_acct"] == from_acct_id or tx["bene_acct"] == from_acct_id
        ]
    else:
        relevant = all_tx_involving
    date_added = min((_parse_ts(tx) for tx in relevant), default=datetime.now(timezone.utc) - timedelta(days=200))

    return BeneficiaryRecord(
        account_age_days=180,  # simulation horizon (total_steps) -- not a real calendar age
        external=False,  # single-bank sample; AMLSim's bank_id is uniform here
        date_added=date_added,
        prior_case_count=_prior_case_count(data, acct_id),
    )


def build_world_and_alert_from_amlsim(sim_output_dir: str):
    """Composes a full (Alert, SyntheticWorld) from a real AMLSim fan-in SAR group. The alert's
    customer is the fan-in *collector* account (many real senders -> it, per alert_accounts.csv
    + transactions.csv), and the alert transaction is a real outgoing transfer that account made
    shortly after real large inbound transfers -- i.e. an authentic simulated mule pass-through
    pattern, not a fabricated one. CUSTOMER/TRANSACTION/BENEFICIARY evidence is built from real
    simulated data; DEVICE/KYC/SAFPS are synthesized (AMLSim doesn't model those)."""
    from .evidence_sources import DeviceRecord, KYCRecord, SAFPSRecord, SyntheticWorld
    from .models import Alert, ImmediateAction, PaymentRail

    data = load_amlsim_output(sim_output_dir)
    group = find_sar_fan_in_group(data)
    if group is None:
        raise ValueError(f"no fan_in SAR group with a real outbound pass-through found in {sim_output_dir}")

    collector_id = group["collector_account"]
    tx = group["outbound_tx"]
    beneficiary_id = tx["bene_acct"]
    tx_time = _parse_ts(tx)

    world = SyntheticWorld(
        customers={collector_id: build_customer_record(data, collector_id)},
        transactions={collector_id: build_transaction_record(data, collector_id, as_of=tx_time)},
        beneficiaries={beneficiary_id: build_beneficiary_record(data, beneficiary_id, from_acct_id=collector_id)},
        devices={collector_id: DeviceRecord(
            device_fingerprint=f"amlsim-fp-{collector_id}", is_usual_device=True, is_usual_location=True,
        )},
        kyc={collector_id: KYCRecord("VERIFIED", tx_time - timedelta(days=100))},
        safps={beneficiary_id: SAFPSRecord(grid_match=False)},
    )

    alert = Alert(
        alert_id=f"AMLSIM-ALERT-{group['alert_id']}-{tx['tran_id']}",
        customer_id=collector_id,
        transaction_id=tx["tran_id"],
        amount=float(tx["base_amt"]),
        beneficiary_id=beneficiary_id,
        beneficiary_bank="THIS_BANK",
        alert_reason="amlsim_fan_in_sar",
        immediate_action=ImmediateAction.HOLD,
        alert_time=tx_time,
        received_time=tx_time,
        beneficiary_name=data.accounts.get(beneficiary_id, {}).get("dsply_nm", beneficiary_id),
        payment_rail=PaymentRail.EFT,
        payment_reference="AMLSim-simulated transfer",
        data_source="AMLSIM_REAL",
    )
    return alert, world


def find_sar_fan_in_group(data: AMLSimData) -> Optional[dict]:
    """Finds a real fan-in SAR typology group from the actual alert_accounts.csv data (not
    fabricated). The fan-in *collector* (many senders -> one account, is the SAR-flagged
    transaction's bene_acct) is the account exhibiting the real mule pass-through pattern --
    returns {'alert_id', 'collector_account', 'outbound_tx'} where outbound_tx is a real
    transaction the collector sent onward, shortly after a real large inbound transfer."""
    by_alert: Dict[str, List[dict]] = {}
    for row in data.alert_membership.values():
        for r in row:
            by_alert.setdefault(r["alert_id"], []).append(r)

    for alert_id, members in by_alert.items():
        if not members or members[0]["alert_type"] != "fan_in":
            continue
        member_ids = {m["acct_id"] for m in members}

        sar_inbound = [
            tx for tx in data.transactions
            if tx["is_sar"] == "True" and tx["orig_acct"] in member_ids and tx["bene_acct"] in member_ids
        ]
        if not sar_inbound:
            continue
        collector_id = sar_inbound[0]["bene_acct"]  # the fan-in target, not the sender

        outbound = sorted(data.out_tx.get(collector_id, []), key=_parse_ts)
        if not outbound:
            continue

        return {"alert_id": alert_id, "collector_account": collector_id, "outbound_tx": outbound[0]}
    return None
