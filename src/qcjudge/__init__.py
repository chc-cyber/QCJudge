"""QCJudge: a scientific evidence auditor for computational chemistry.

The package root re-exports the domain types and the audit entry point. Nothing here imports
a web framework, an LLM SDK, or the command-line layer.
"""

from qcjudge.audit.engine import TOOL_VERSION, audit
from qcjudge.domain.assessment import AssessmentStatus
from qcjudge.domain.audit import AuditReport
from qcjudge.domain.evidence import EvidenceInventory
from qcjudge.domain.question import QuestionFamily, ResearchQuestion

__version__ = TOOL_VERSION

__all__ = [
    "TOOL_VERSION",
    "AssessmentStatus",
    "AuditReport",
    "EvidenceInventory",
    "QuestionFamily",
    "ResearchQuestion",
    "__version__",
    "audit",
]
