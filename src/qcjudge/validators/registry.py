"""Rule registry mapping ``implementation_key`` to a callable.

A protocol that names a rule nobody implements must fail loudly rather than silently skip
the check, so :func:`resolve` raises instead of returning a default.
"""

from __future__ import annotations

from collections.abc import Callable

from qcjudge.domain.context import AuditContext
from qcjudge.domain.validation import RuleOutcome
from qcjudge.errors import UnknownValidationRuleError

type RuleFn = Callable[[AuditContext], RuleOutcome]

_REGISTRY: dict[str, RuleFn] = {}


def register(key: str) -> Callable[[RuleFn], RuleFn]:
    """Decorator registering a rule under a stable ``implementation_key``."""

    def _decorator(function: RuleFn) -> RuleFn:
        if key in _REGISTRY:
            raise RuntimeError(f"Duplicate validator registration for {key!r}")
        _REGISTRY[key] = function
        return function

    return _decorator


def resolve(key: str) -> RuleFn:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownValidationRuleError(key) from None


def registered_keys() -> frozenset[str]:
    return frozenset(_REGISTRY)
