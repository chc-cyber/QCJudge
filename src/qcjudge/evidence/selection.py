"""Select one explicitly associated target before reasoning about evidence.

Calculation IDs identify producers' results. A source link associates an external analysis
with the calculation it describes; it never merges their facts or their provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

from qcjudge.domain.evidence import EvidenceInventory, EvidenceOrigin, Subject
from qcjudge.domain.question import ResearchQuestion


@dataclass(frozen=True, slots=True)
class InventorySelection:
    inventory: EvidenceInventory
    calculation_ids: tuple[str, ...]
    issue: str | None = None


def select_inventory(
    question: ResearchQuestion, inventory: EvidenceInventory
) -> InventorySelection:
    """Refuse ambiguous targets and keep only the chosen calculation's linked results."""
    subjects: dict[str, list[Subject]] = {}
    supplied_subjects = tuple(fact.subject for fact in inventory.facts) + tuple(
        item.subject for item in inventory.unavailable
    )
    for subject in supplied_subjects:
        subjects.setdefault(subject.calculation_id, []).append(subject)
    all_ids = tuple(sorted(subjects))

    def unresolved(message: str) -> InventorySelection:
        # Retain the supplied calculations for execution checks and inspection. The
        # protocol-declared association gate prevents them supporting scientific claims.
        return InventorySelection(inventory, all_ids, message)

    if not subjects:
        requested = question.bindings.get("calculation_id")
        if requested is not None:
            return unresolved(f"The selected calculation {requested!r} was not supplied.")
        return InventorySelection(inventory, ())

    parents: dict[str, str | None] = {}
    for calculation_id, declared in subjects.items():
        links = {subject.source_calculation_id for subject in declared}
        if len(links) != 1:
            return unresolved(f"Conflicting source links were supplied for {calculation_id!r}.")
        parents[calculation_id] = next(iter(links))

    roots: dict[str, str] = {}
    for calculation_id in subjects:
        visited: set[str] = set()
        current = calculation_id
        while parents[current] is not None:
            if current in visited:
                return unresolved(f"The source links contain a cycle at {current!r}.")
            visited.add(current)
            parent = parents[current]
            assert parent is not None
            if parent not in parents:
                return unresolved(
                    f"Calculation {current!r} names source {parent!r}, which was not supplied."
                )
            current = parent
        roots[calculation_id] = current

    requested = question.bindings.get("calculation_id")
    if requested is not None:
        if requested not in roots:
            return unresolved(f"The selected calculation {requested!r} was not supplied.")
        target = roots[requested]
    else:
        unique_roots = set(roots.values())
        if len(unique_roots) != 1:
            return unresolved(
                "Multiple unassociated calculations were supplied. Select a calculation "
                "with --target (or context calculation_id), and declare source_calculation_id "
                "on analyses that describe it; unrelated results cannot be combined."
            )
        target = next(iter(unique_roots))

    selected_ids = {key for key, root in roots.items() if root == target}
    for calculation_id in sorted(selected_ids):
        for subject in subjects[calculation_id]:
            for name in ("molecule", "state"):
                supplied = getattr(subject, name)
                expected = question.bindings.get(name)
                if supplied is not None and expected is not None and supplied != expected:
                    return unresolved(
                        f"Calculation {calculation_id!r} declares {name}={supplied!r}, "
                        f"but the question asks about {expected!r}."
                    )

    facts = tuple(fact for fact in inventory.facts if fact.subject.calculation_id in selected_ids)
    fact_ids = {fact.id for fact in facts}
    evidence = tuple(
        item for item in inventory.evidence
        if (item.fact_ids and set(item.fact_ids) <= fact_ids)
        or item.origin is EvidenceOrigin.USER_ASSERTION
    )
    return InventorySelection(
        EvidenceInventory(
            facts=facts,
            evidence=evidence,
            unavailable=tuple(
                item for item in inventory.unavailable
                if item.subject.calculation_id in selected_ids
            ),
        ),
        tuple(sorted(selected_ids)),
    )
