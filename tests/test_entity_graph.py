from fraud_copilot.entity_graph import find_links
from fraud_copilot.pipeline import process_alert
from fraud_copilot.storage import Store

from .factories import clean_world, make_alert


def test_no_links_for_a_lone_case():
    store = Store()
    world = clean_world()
    case = process_alert(make_alert(), world, store)
    links = find_links(case, store)
    assert links == []


def test_one_hop_link_via_shared_device_when_target_has_prior_cases():
    store = Store()

    world1 = clean_world()
    case1 = process_alert(make_alert(), world1, store)

    world2 = clean_world()
    world2.customers["CUST-2"] = world2.customers.pop("CUST-1")
    world2.transactions["CUST-2"] = world2.transactions.pop("CUST-1")
    world2.devices["CUST-2"] = world2.devices.pop("CUST-1")
    world2.kyc["CUST-2"] = world2.kyc.pop("CUST-1")
    world2.customers["CUST-2"].prior_case_count = 2  # so it's surfaced (LLD sec 7.3)
    world2.devices["CUST-2"].device_fingerprint = "fp-usual"  # same device as case1 --
    world2.devices["CUST-2"].phone_number = "0839999999"  # but different phone/ip, so the
    world2.devices["CUST-2"].ip_address = "41.1.1.1"      # match is unambiguously DEVICE
    world2.beneficiaries["BEN-1"].external = True  # different beneficiary too (not linked)
    world2.beneficiaries["BEN-1"].prior_case_count = 0

    alert2 = make_alert(alert_id="ALERT-2", transaction_id="TXN-2", customer_id="CUST-2",
                         beneficiary_id="BEN-OTHER")
    world2.beneficiaries["BEN-OTHER"] = world2.beneficiaries.pop("BEN-1")
    case2 = process_alert(alert2, world2, store)

    links = find_links(case1, store)
    linked_ids = {l.linked_entity_id for l in links}
    assert "CUST-2" in linked_ids
    link = next(l for l in links if l.linked_entity_id == "CUST-2")
    assert link.shared_attribute == "DEVICE"
    assert link.hops == 1


def test_link_not_surfaced_when_target_has_no_prior_cases():
    store = Store()
    world1 = clean_world()
    case1 = process_alert(make_alert(), world1, store)

    world2 = clean_world()
    world2.customers["CUST-2"] = world2.customers.pop("CUST-1")
    world2.transactions["CUST-2"] = world2.transactions.pop("CUST-1")
    world2.devices["CUST-2"] = world2.devices.pop("CUST-1")
    world2.kyc["CUST-2"] = world2.kyc.pop("CUST-1")
    world2.customers["CUST-2"].prior_case_count = 0  # no prior cases -> not surfaced
    world2.devices["CUST-2"].device_fingerprint = "fp-usual"

    alert2 = make_alert(alert_id="ALERT-2", transaction_id="TXN-2", customer_id="CUST-2")
    process_alert(alert2, world2, store)

    links = find_links(case1, store)
    assert links == []
