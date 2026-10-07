"""Projecting parser observations into facts, and facts into evidence."""

from qcjudge.evidence.derivation import derive_evidence, with_derived_evidence
from qcjudge.evidence.facts import facts_from_parse_results
from qcjudge.evidence.matching import (
    admissible_evidence_ids,
    assess_all,
    candidate_evidence_ids,
    satisfied_groups,
)

__all__ = [
    "admissible_evidence_ids",
    "assess_all",
    "candidate_evidence_ids",
    "derive_evidence",
    "facts_from_parse_results",
    "satisfied_groups",
    "with_derived_evidence",
]
