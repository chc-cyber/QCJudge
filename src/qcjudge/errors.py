"""Exception hierarchy for the deterministic core.

Everything QCJudge refuses to do on purpose raises a subclass of QCJudgeError, so callers
can separate deliberate refusals from programming mistakes.
"""

from __future__ import annotations


class QCJudgeError(Exception):
    """Base class for every deliberate QCJudge error."""


class DomainError(QCJudgeError, ValueError):
    """A domain object was constructed with inconsistent data."""


class UnresolvedBindingError(DomainError):
    """A question did not supply a placeholder that a protocol claim requires."""

    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__("Question context does not supply: " + ", ".join(missing))


class ProtocolError(QCJudgeError, ValueError):
    """A protocol declaration is internally inconsistent or incomplete."""


class UnknownValidationRuleError(ProtocolError):
    """A protocol declares an implementation_key that no validator implements."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"No validator is registered for implementation_key {key!r}")


class InventoryError(DomainError):
    """An evidence inventory failed a referential-integrity check."""


class AdapterFormatError(QCJudgeError, ValueError):
    """An imported analysis file is not in the documented format.

    Raised rather than guessed at: an import is third-party input, and a value read from the
    wrong field would enter the audit indistinguishable from a computed one.
    """


class UnknownExportedQuantityError(AdapterFormatError):
    """An imported file names a quantity that no FactKey registers, or none this seam carries.

    The accepted names are listed, because an export is written by hand or by a small conversion
    script and the useful thing to say is what it should have written.
    """

    def __init__(
        self, quantity: str, *, source: str, accepted: tuple[str, ...] = ()
    ) -> None:
        self.quantity = quantity
        self.accepted = accepted
        detail = (
            " Imported values must name a registered fact key, so a typo cannot become "
            "silently missing evidence."
        )
        if accepted:
            detail += " This seam carries: " + ", ".join(accepted) + "."
        super().__init__(f"{source} exports an unknown quantity {quantity!r}.{detail}")


class WrongUnitError(AdapterFormatError):
    """An imported value is stated in a unit the fact key does not use."""

    def __init__(self, quantity: str, unit: object, expected: str) -> None:
        self.quantity = quantity
        super().__init__(
            f"{quantity!r} was stated in {unit!r}, but this fact is recorded in "
            f"{expected!r}. Convert the value before exporting rather than having the audit "
            "guess which unit it is in."
        )
