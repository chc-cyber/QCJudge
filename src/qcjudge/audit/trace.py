"""The reasoning graph, so a report can answer "why did it say that".

Edges are plain string pairs. V0.1 keeps identity as stable strings rather than introducing
an entity framework: the graph stays inspectable and serialisable, and the cost of a richer
model is not yet justified.
"""

from __future__ import annotations

from collections.abc import Sequence

from qcjudge.domain.assessment import EvidenceAssessment
from qcjudge.domain.audit import TraceEdge
from qcjudge.domain.evidence import EvidenceInventory
from qcjudge.domain.protocol import ScientificProtocol
from qcjudge.domain.question import ResearchQuestion


def build_trace(
    question: ResearchQuestion,
    protocol: ScientificProtocol,
    inventory: EvidenceInventory,
    requirement_assessments: Sequence[EvidenceAssessment],
) -> tuple[TraceEdge, ...]:
    """Collect every edge from question through to the facts that carried a status."""
    edges: list[TraceEdge] = []

    def link(source: str, relation: str, target: str) -> None:
        edge = TraceEdge(source, relation, target)
        if edge not in edges:
            edges.append(edge)

    for hypothesis in protocol.hypotheses:
        link(f"question:{question.family.value}", "is_made_checkable_by", hypothesis.id)
    for claim in protocol.claims:
        link(claim.hypothesis_id, "is_made_checkable_by", claim.id)
    for requirement in protocol.requirements:
        link(requirement.claim_id, "requires", requirement.id)
        for dependency in requirement.dependencies:
            link(dependency, "must_precede", requirement.id)
    for item in inventory.evidence:
        for fact_id in item.fact_ids:
            link(item.id, "cites", fact_id)
        if item.provenance is not None:
            link(item.id, "recorded_in", item.provenance.source_file)
    for fact in inventory.facts:
        link(fact.id, "recorded_in", fact.provenance.source_file)
    for assessment in requirement_assessments:
        for evidence_id in assessment.evidence_ids:
            link(assessment.requirement_id, "is_met_by", evidence_id)
        if assessment.met_via_alternative is not None:
            link(
                assessment.requirement_id,
                "is_satisfied_by_alternative",
                assessment.met_via_alternative,
            )
        for blocked in assessment.blocked_by:
            link(blocked, "blocks", assessment.requirement_id)
    return tuple(edges)
