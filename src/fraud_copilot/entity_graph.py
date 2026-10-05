"""Entity graph (LLD.md sec 7). A minimal labelled-property graph, pure Python (no external
graph library) -- node = (type, key), edge = shared attribute between two nodes. The node/edge
shape and the 1-2 hop traversal query match LLD sec 7.1/7.3 exactly, so swapping this module's
storage for a real Amazon Neptune driver later changes only where nodes/edges are written and
queried, not the query shape itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .models import Case, EvidenceSource
from .storage import Store

NodeKey = Tuple[str, str]  # (node_type, key) -- node_type in CUSTOMER/ACCOUNT/DEVICE/PHONE/IP


@dataclass(frozen=True)
class GraphLink:
    """LLD.md sec 7.2."""

    linked_entity_type: str
    linked_entity_id: str
    shared_attribute: str
    hops: int
    narrative_hint: str


class Graph:
    def __init__(self) -> None:
        self._edges: Dict[NodeKey, Dict[NodeKey, str]] = {}  # node -> {neighbor: edge_type}
        self._prior_case_count: Dict[NodeKey, int] = {}

    def add_node(self, node: NodeKey, prior_case_count: int = 0) -> None:
        self._edges.setdefault(node, {})
        self._prior_case_count[node] = max(self._prior_case_count.get(node, 0), prior_case_count)

    def add_edge(self, a: NodeKey, b: NodeKey, edge_type: str) -> None:
        self.add_node(a)
        self.add_node(b)
        self._edges[a][b] = edge_type
        self._edges[b][a] = edge_type

    def prior_case_count(self, node: NodeKey) -> int:
        return self._prior_case_count.get(node, 0)

    def neighbors(self, node: NodeKey) -> Dict[NodeKey, str]:
        return self._edges.get(node, {})

    def has_node(self, node: NodeKey) -> bool:
        return node in self._edges


def build_graph(store: Store) -> Graph:
    """Builds the graph from every case's latest snapshot currently in the store."""
    graph = Graph()

    for case in store.all_cases():
        if not case.latest_snapshot_id:
            continue
        snapshot = store.get_snapshot(case.latest_snapshot_id)
        if snapshot is None:
            continue
        by_source = {r.source: r for r in snapshot.sources}

        customer_node: NodeKey = ("CUSTOMER", case.customer_id)
        customer_result = by_source.get(EvidenceSource.CUSTOMER)
        customer_prior_cases = (
            customer_result.data.get("prior_case_count", 0)
            if customer_result and customer_result.data else 0
        )
        graph.add_node(customer_node, prior_case_count=customer_prior_cases)

        beneficiary_result = by_source.get(EvidenceSource.BENEFICIARY)
        if beneficiary_result and beneficiary_result.data:
            for beneficiary_id in case.beneficiary_ids:
                account_node: NodeKey = ("ACCOUNT", beneficiary_id)
                graph.add_node(
                    account_node,
                    prior_case_count=beneficiary_result.data.get("prior_case_count", 0),
                )
                graph.add_edge(customer_node, account_node, "ACCOUNT")

        device_result = by_source.get(EvidenceSource.DEVICE)
        if device_result and device_result.data:
            fp = device_result.data.get("device_fingerprint")
            if fp:
                graph.add_edge(customer_node, ("DEVICE", fp), "DEVICE")
            phone = device_result.data.get("phone_number")
            if phone:
                graph.add_edge(customer_node, ("PHONE", phone), "PHONE")
            ip = device_result.data.get("ip_address")
            if ip:
                graph.add_edge(customer_node, ("IP", ip), "IP")

    return graph


def _entities_sharing_an_attribute_with(graph: Graph, node: NodeKey) -> Dict[NodeKey, str]:
    """Other CUSTOMER/ACCOUNT entities that share a DEVICE/PHONE/IP/ACCOUNT attribute with
    `node` -- i.e. one 'hop' in the design's people-oriented sense (LLD sec 7.3), even though
    it is two edges away structurally (node -> shared attribute -> other entity)."""
    result: Dict[NodeKey, str] = {}
    for attr_node, edge_type in graph.neighbors(node).items():
        attr_type, _ = attr_node
        if attr_type not in ("DEVICE", "PHONE", "IP", "ACCOUNT"):
            continue
        for other, _edge_type2 in graph.neighbors(attr_node).items():
            if other == node:
                continue
            other_type, _ = other
            if other_type not in ("CUSTOMER", "ACCOUNT"):
                continue
            result[other] = edge_type  # last attribute type checked wins if multiple match
    return result


def find_links(case: Case, store: Store, graph: Optional[Graph] = None) -> List[GraphLink]:
    """1-2 hop traversal from this case's customer node (LLD sec 7.3), filtered to linked nodes
    with prior_case_count >= 1. 1-hop = another entity sharing an attribute directly with this
    case's customer; 2-hop = an entity reached through exactly one such intermediate entity."""
    if graph is None:
        graph = build_graph(store)

    start: NodeKey = ("CUSTOMER", case.customer_id)
    if not graph.has_node(start):
        return []

    links: List[GraphLink] = []
    seen: Set[NodeKey] = {start}

    hop1 = _entities_sharing_an_attribute_with(graph, start)
    for node, edge_type in hop1.items():
        seen.add(node)
        _maybe_add_link(graph, links, node, edge_type, hops=1)

    for node in list(hop1.keys()):
        for node2, edge_type2 in _entities_sharing_an_attribute_with(graph, node).items():
            if node2 in seen:
                continue
            seen.add(node2)
            _maybe_add_link(graph, links, node2, edge_type2, hops=2)

    return links


def _maybe_add_link(graph: Graph, links: List[GraphLink], node: NodeKey, edge_type: str, hops: int) -> None:
    node_type, node_id = node
    if node_type not in ("CUSTOMER", "ACCOUNT"):
        return  # only surface actual entities (customers/accounts), not the shared attribute itself
    if graph.prior_case_count(node) < 1:
        return
    links.append(GraphLink(
        linked_entity_type=node_type,
        linked_entity_id=node_id,
        shared_attribute=edge_type,
        hops=hops,
        narrative_hint=(
            f"Linked via shared {edge_type.lower()} to {node_type.lower()} {node_id}, "
            f"which has {graph.prior_case_count(node)} prior case(s)"
        ),
    ))
