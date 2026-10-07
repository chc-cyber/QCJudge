"""Deterministic validation rules and the registry that resolves them.

Importing this package registers every built-in rule. Rules read the inventory through
:class:`~qcjudge.domain.context.AuditContext` and return a
:class:`~qcjudge.domain.validation.RuleOutcome`; they never see a protocol rule id, and they
never write anywhere.
"""

from qcjudge.validators import execution, methodology, target_state
from qcjudge.validators.registry import RuleFn, register, registered_keys, resolve

__all__ = [
    "RuleFn",
    "execution",
    "methodology",
    "register",
    "registered_keys",
    "resolve",
    "target_state",
]
