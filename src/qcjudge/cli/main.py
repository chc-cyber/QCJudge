"""QCJudge command-line entry point.

Thin by design: it assembles a question and an inventory, calls the engine, and hands the
report to a renderer. It contains no scientific logic.

``--evidence`` records a *user assertion* -- "I performed this analysis" -- which the domain
caps at WEAK and INDIRECT. Such an assertion is therefore recorded honestly but cannot
satisfy a requirement that demands stronger, more direct evidence.

Two channels carry what only the researcher can observe, and neither is evidence:

``--condition KEY=VALUE``
    A fact about their own calculation that no output file states: the partition they chose,
    the character they assigned. A protocol may name one of these keys to have an expert
    boundary tested rather than guessed. A condition no protocol names is still recorded, so
    the report shows what the audit was told even when nothing acted on it.

``--expert-review REQUIREMENT_ID``
    The researcher states that a declared expert boundary has been reached.

Exit codes describe the *run*, not the verdict: ``0`` whenever an audit was produced and
printed, including one whose evidence is insufficient, because the report is the deliverable
and its status is in the report. Use ``--format json`` and read
``evidence.overall_status`` to branch on the finding. ``2`` means the audit could not be
produced at all.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from qcjudge.adapters import JsonAnalysisAdapter
from qcjudge.audit import audit
from qcjudge.domain.context import ExpertReviewFlag
from qcjudge.domain.evidence import (
    Evidence,
    EvidenceDirectness,
    EvidenceInventory,
    EvidenceOrigin,
    EvidenceStrength,
    EvidenceType,
)
from qcjudge.domain.question import (
    Hypothesis,
    MethodAssumption,
    QuestionFamily,
    ResearchQuestion,
)
from qcjudge.errors import QCJudgeError
from qcjudge.evidence import facts_from_parse_results
from qcjudge.parsers import OrcaOutputParser
from qcjudge.protocols import get_protocol
from qcjudge.render import report_to_text, to_json

_PROG = "qcjudge"
# 0: an audit was produced. 2: it could not be produced, or the invocation was wrong. No code
# in between, so a caller can never mistake a finding for a failure to run.
_EXIT_AUDITED = 0
_EXIT_UNUSABLE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=_PROG)
    commands = parser.add_subparsers(dest="command", required=True)
    audit_parser = commands.add_parser("audit", help="audit an evidence inventory")
    audit_parser.add_argument(
        "--question",
        required=True,
        choices=[family.value for family in QuestionFamily],
        metavar="FAMILY",
        help="which question family to audit against, e.g. transition_state",
    )
    audit_parser.add_argument(
        "--ask",
        default=None,
        metavar="TEXT",
        help=(
            "the question in your own words, recorded verbatim in the report; without it the "
            "report states the protocol's own hypothesis"
        ),
    )
    audit_parser.add_argument(
        "--input", required=True, type=Path, help="an output file or a directory of them"
    )
    audit_parser.add_argument(
        "--context",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="question context used to bind protocol claims, e.g. molecule=molA",
    )
    audit_parser.add_argument(
        "--assumption",
        action="append",
        default=[],
        metavar="TEXT",
        help="a premise the audit rests on, recorded verbatim",
    )
    audit_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        metavar="TYPE",
        help="assert that an analysis was performed; recorded as a user assertion",
    )
    audit_parser.add_argument(
        "--condition",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "report something only you can observe, e.g. donor_acceptor_partition=ambiguous; "
            "a protocol may test it to reach an expert boundary"
        ),
    )
    audit_parser.add_argument(
        "--expert-review",
        action="append",
        default=[],
        metavar="REQUIREMENT_ID",
        help="state that a declared expert boundary has been reached for a requirement",
    )
    audit_parser.add_argument(
        "--analysis",
        action="append",
        default=[],
        type=Path,
        metavar="FILE",
        help=(
            "import an external analysis, such as a hole-electron or spin-orbit export; its "
            "values are attributed to the tool that produced them, not to the calculation"
        ),
    )
    audit_parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _parse_pairs(pairs: Sequence[str], option: str) -> tuple[tuple[str, str], ...]:
    parsed: list[tuple[str, str]] = []
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"{option} expects KEY=VALUE, received {pair!r}")
        parsed.append((key.strip(), value.strip()))
    return tuple(parsed)


def _parse_context(pairs: Sequence[str]) -> tuple[tuple[str, str], ...]:
    return _parse_pairs(pairs, "--context")


def _parse_conditions(pairs: Sequence[str]) -> Mapping[str, str]:
    conditions = _parse_pairs(pairs, "--condition")
    keys = [key for key, _ in conditions]
    if len(set(keys)) != len(keys):
        raise ValueError("--condition was given the same key more than once")
    return dict(conditions)


def _expert_reviews(
    requirement_ids: Sequence[str], family: QuestionFamily, reporter: str | None
) -> tuple[ExpertReviewFlag, ...]:
    """Turn ``--expert-review`` into flags, refusing a requirement the protocol does not have.

    A boundary that does not exist cannot be reached, and silently accepting the id would let
    a typo look like a recorded judgement.
    """
    protocol = get_protocol(family)
    known = {requirement.id: requirement for requirement in protocol.requirements}
    flags: list[ExpertReviewFlag] = []
    for requirement_id in requirement_ids:
        requirement = known.get(requirement_id)
        if requirement is None:
            raise ValueError(
                f"--expert-review names an unknown requirement {requirement_id!r} for "
                f"{family.value}; known: {', '.join(sorted(known))}"
            )
        declared = requirement.expert_review_when
        if declared is None:
            raise ValueError(
                f"requirement {requirement_id!r} declares no expert boundary, so no boundary "
                "can be reported for it"
            )
        flags.append(
            ExpertReviewFlag(
                requirement_id=requirement_id,
                reported_condition=declared,
                reported_by=reporter,
            )
        )
    return tuple(flags)


def _user_assertions(types: Sequence[str]) -> tuple[Evidence, ...]:
    """Record assertions of completed analyses, with no file provenance attached."""
    return tuple(
        Evidence(
            id=f"assertion-{index}",
            evidence_type=EvidenceType(raw),
            description=(
                f"The user asserts that {raw} was performed outside QCJudge. No file "
                "provenance accompanies this statement."
            ),
            fact_ids=(),
            strength=EvidenceStrength.WEAK,
            directness=EvidenceDirectness.INDIRECT,
            origin=EvidenceOrigin.USER_ASSERTION,
        )
        for index, raw in enumerate(types, start=1)
    )


def _question(args: argparse.Namespace) -> ResearchQuestion:
    """Assemble the question, keeping the researcher's own words when they gave any.

    The report must state the question that was actually asked. Falling back to the protocol's
    hypothesis keeps the field populated, but it is a fallback rather than a substitute: an
    audit of "is this a TADF emitter?" must not be presented as an audit of whatever the
    protocol happens to assert.
    """
    family = QuestionFamily(args.question)
    protocol = get_protocol(family)
    hypotheses = tuple(
        Hypothesis(item.id, item.statement) for item in protocol.hypotheses
    )
    assumptions = tuple(
        MethodAssumption(f"assumption-{index}", text)
        for index, text in enumerate(args.assumption, start=1)
    )
    asked = args.ask.strip() if isinstance(args.ask, str) else ""
    if args.ask is not None and not asked:
        raise ValueError("--ask was given an empty question")
    return ResearchQuestion(
        family=family,
        text=asked or protocol.hypotheses[0].statement,
        hypotheses=hypotheses,
        context=_parse_context(args.context),
        assumptions=assumptions,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        question = _question(args)
        parser = OrcaOutputParser()
        paths = sorted(args.input.glob("*.out")) if args.input.is_dir() else [args.input]
        if not paths:
            print(f"{_PROG}: no input files matched {args.input}", file=sys.stderr)
            return _EXIT_UNUSABLE
        results = tuple(parser.parse(path) for path in paths)
        if all(not result.diagnostics.is_usable for result in results):
            print(
                f"{_PROG}: none of the {len(results)} input file(s) were recognised as ORCA "
                "output, so nothing could be read.",
                file=sys.stderr,
            )
            return _EXIT_UNUSABLE

        # Imported analyses are read the same way a calculation's output is, and their values
        # keep a producer of their own, so the report can say which numbers the calculation
        # emitted and which an external tool supplied.
        supported = set(parser.supported_keys)
        for path in args.analysis or ():
            imported, carried = JsonAnalysisAdapter().parse_all(path)
            results = (*results, *imported)
            supported |= carried
        facts, absences = facts_from_parse_results(
            results, supported_keys=frozenset(supported)
        )
        supplied = EvidenceInventory(
            facts=facts,
            evidence=_user_assertions(args.evidence),
            unavailable=absences,
        )
        report = audit(
            question,
            supplied,
            conditions=_parse_conditions(args.condition),
            expert_reviews=_expert_reviews(
                args.expert_review, question.family, reporter=None
            ),
        )
    except QCJudgeError as error:
        print(f"{_PROG}: {error}", file=sys.stderr)
        return _EXIT_UNUSABLE
    except (ValueError, OSError) as error:
        print(f"{_PROG}: {error}", file=sys.stderr)
        return _EXIT_UNUSABLE

    for result in results:
        for warning in result.diagnostics.warnings:
            print(f"{_PROG}: {result.source_file}: {warning}", file=sys.stderr)

    if args.format == "json":
        print(to_json(report), end="")
    else:
        print(report_to_text(report), end="")
    # The audit was produced, so the run succeeded. A finding of insufficient evidence is a
    # finding, not a failure, and the caller reads it from the report.
    return _EXIT_AUDITED


if __name__ == "__main__":
    raise SystemExit(main())
