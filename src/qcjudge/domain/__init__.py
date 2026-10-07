"""Typed concepts used throughout QCJudge.

Nothing in this package imports any other QCJudge package, and nothing here performs I/O.
"""

from qcjudge.domain.assessment import (
    AssessmentStatus,
    ClaimAssessment,
    EvidenceAssessment,
    HypothesisAssessment,
)
from qcjudge.domain.audit import AuditReport, Recommendation, TraceEdge
from qcjudge.domain.common import (
    EpistemicKind,
    Provenance,
    TruthValue,
    UnavailableReason,
)
from qcjudge.domain.context import AuditContext
from qcjudge.domain.evidence import (
    Evidence,
    EvidenceDirectness,
    EvidenceGroup,
    EvidenceInventory,
    EvidenceOrigin,
    EvidenceRequirement,
    EvidenceStrength,
    EvidenceType,
    ExtractedFact,
    FactKey,
    GroupSatisfaction,
    RequirementLevel,
    RequirementRole,
    Subject,
    UnavailableFact,
)
from qcjudge.domain.protocol import RecommendationSpec, ScientificProtocol
from qcjudge.domain.question import (
    Claim,
    Hypothesis,
    Interpretation,
    MethodAssumption,
    QuestionFamily,
    ResearchQuestion,
    bind,
)
from qcjudge.domain.validation import (
    ValidationResult,
    ValidationRuleSpec,
    ValidationScope,
    ValidationStatus,
)

__all__ = [
    "AssessmentStatus",
    "AuditContext",
    "AuditReport",
    "Claim",
    "ClaimAssessment",
    "EpistemicKind",
    "Evidence",
    "EvidenceAssessment",
    "EvidenceDirectness",
    "EvidenceGroup",
    "EvidenceInventory",
    "EvidenceOrigin",
    "EvidenceRequirement",
    "EvidenceStrength",
    "EvidenceType",
    "ExtractedFact",
    "FactKey",
    "GroupSatisfaction",
    "Hypothesis",
    "HypothesisAssessment",
    "Interpretation",
    "MethodAssumption",
    "Provenance",
    "QuestionFamily",
    "Recommendation",
    "RecommendationSpec",
    "RequirementLevel",
    "RequirementRole",
    "ResearchQuestion",
    "ScientificProtocol",
    "Subject",
    "TraceEdge",
    "TruthValue",
    "UnavailableFact",
    "UnavailableReason",
    "ValidationResult",
    "ValidationRuleSpec",
    "ValidationScope",
    "ValidationStatus",
    "bind",
]
