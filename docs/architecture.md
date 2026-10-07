# V0.1 architecture

## Decision

QCJudge uses a layered, dependency-light Python package with an immutable domain core.
Protocol V1 declarations are typed Python data, not YAML. Python provides construction-time
validation, safe refactoring, and direct testability without a runtime schema dependency.
Serialization can be added at the boundary later without making serialized data authoritative.

The intended dependency direction is:

```text
CLI -> audit engine -> domain + protocols + validators
                    -> parser interfaces <- ORCA parser
                    -> adapter interfaces <- Multiwfn/imported analyses
```

Parsers produce provenance-bearing observations. They do not assess claims. Validators make
bounded, deterministic checks. The audit engine maps evidence to protocol requirements and
preserves the trace from question through claims, requirements, facts, and assessments.

## Core model

- `ResearchQuestion` selects one supported family and contains explicit `Claim` objects.
- `ExtractedFact` is an observation or computed value with provenance; `None` represents unknown.
- `Hypothesis` groups the claims that make a broad proposition checkable, so a report can say
  "claim A supported, claim B unevidenced, therefore the hypothesis is not established".
- `Evidence` cites facts and records strength, directness, and origin.
- `EvidenceRequirement` belongs to a claim and declares necessity, role (substantive or
  prerequisite), accepted evidence types, minimum strength and directness, required facts,
  dependencies, group membership, gating and contradicting rules, and expert-review boundaries.
- `EvidenceGroup` expresses alternative evidence structurally: a group is satisfied by any one
  of its members, so symmetry is a property of the model rather than a pair of hand-maintained
  cross-references.
- `ScientificProtocol` is an immutable, versioned graph of hypotheses, claims, requirements,
  groups, rule specs, recommendations, background interpretations, and limitations.
- `ValidationResult` reports execution, structural, or methodology checks independently. The
  three scopes are kept apart because merging them would let one leak into another: a converged
  minimum is a successful calculation that is not a saddle point.
- `EvidenceAssessment`, `ClaimAssessment`, and `HypothesisAssessment` state coverage and rationale.
- `AuditReport` carries the question, the inventory it was judged against, the validation
  results, the trace edges, and the versions, so "why did it say that" is answerable from the
  report alone. It aggregates the axes without reducing them to one score.

Identity is represented by stable string IDs in V0.1. This keeps graph edges explicit and output
serializable while avoiding a premature entity framework.

## Determinism and judgment boundary

Deterministic code may parse explicit output, compare values, count frequencies, test convergence
flags, check method consistency, validate protocol graph integrity, and map declared evidence types.
Every such conclusion must cite inputs or state that they are unknown.

The core must not infer scientific truth, invent absent facts, decide ambiguous donor/acceptor
partitions, assert universal numerical cutoffs, or turn a proxy into a stronger claim. Rules return
`UNKNOWN` when inputs are absent and `REQUIRES_EXPERT_REVIEW` when a conclusion depends on
system-specific interpretation. A future LLM may translate questions or explain completed reports,
but its output cannot overwrite parsed facts, validation results, or evidence coverage.

## Initial protocol schemas

Each protocol declares a question family, claims, evidence requirements, accepted evidence types,
requirement dependencies/alternatives, methodology and execution rule specifications, conditional
recommendations, limitations, and a semantic version.

- Charge transfer requires a target-state assignment and spatial redistribution evidence;
  method-sensitivity evidence is recommended. Energies alone are insufficient.
- TADF requires relevant singlet/triplet energetics plus RISC coupling or kinetics evidence;
  a radiative-channel characterization is recommended. A small gap alone is insufficient.
- Transition state requires a converged first-order saddle point and reaction-coordinate/pathway
  evidence. One imaginary frequency alone does not establish pathway identity.

## Package boundaries

`domain/`, `protocols/`, `parsers/`, `validators/`, `evidence/`, `audit/`, `render/` and `cli/`
all exist and carry working behaviour. `adapters/` does not exist yet: the seam is planned for a
milestone after M3, and empty placeholder modules are intentionally avoided. The milestone order
and the current gap between declarations and behavior are tracked in
[docs/v0.1-plan.md](v0.1-plan.md).

Every module that leaves the package ships with the tests that hold it in place. Two boundaries
have proved easy to test on one side only and therefore worth calling out:

- **parser to audit.** Testing the engine against hand-built inventories proves the reasoning;
  it cannot show what status a real file produces. `tests/test_end_to_end.py` crosses the
  boundary on the real corpus for exactly this reason.
- **declaration to behaviour.** A field a protocol declares but nothing reads is worse than a
  missing field, because the declaration reads as an implemented control. `expert_review_when`
  is the standing example (D-31).

## Failure modes and technical-debt controls

- **Proxy inflation:** treating a computed proxy as proof of a stronger claim. Control with
  epistemic categories and requirement-level assessments.
- **Unknown becomes false:** absent parser data may be misread as failure. Preserve `UNKNOWN` and
  test missing-data paths.
- **Threshold overreach:** fixed scientific cutoffs can be method/system dependent. Store only
  defensible checks; otherwise require expert review.
- **Parser/auditor coupling:** format-specific assumptions can leak into science rules. Exchange
  typed facts through interfaces and contract-test parsers.
- **Protocol drift:** changing rules can make reports irreproducible. Version protocols and record
  protocol version in reports and derived provenance.
- **Stringly typed evidence:** V0.1 evidence-type strings ease extension but risk typos. Introduce a
  registry or validated plugin namespace before third-party protocols are supported.
- **Alternative/dependency semantics:** complex Boolean evidence graphs can become opaque. Keep V1
  semantics narrow and add graph/cycle validation before the audit engine consumes them.
- **Overconfident prose:** rendering can exceed structured conclusions. Generate templates from the
  audit state and test that explanations preserve status and uncertainty.
- **Fixture realism:** synthetic outputs may miss vendor quirks. Add licensed/redacted real-world
  fixtures and parser fuzz/regression tests incrementally.

## Minimal dependencies

The runtime core uses only the Python standard library. Development extras are pytest, Ruff, and
mypy; Hatchling builds the package. A later ORCA parser adapter may optionally depend on cclib after
its capability and license are reviewed. CLI parsing should begin with `argparse`; richer UI
dependencies are not justified yet.

## Test strategy

1. Domain invariants and protocol graph validation with fast unit tests.
2. Audit truth-table tests proving execution status and evidence adequacy are orthogonal.
3. Parser contract tests using minimal synthetic ORCA fixtures, including missing and malformed data.
4. **End-to-end tests that drive one real file through parse, project, derive, match and aggregate**, because steps 2 and 3 each pass while the composed result is wrong.
5. Protocol scenario tests for all cases in the scientific scope document.
6. **Golden structured-report tests** pinning the JSON report's structure, plus byte-for-byte
   snapshots of the human rendering. The shape is recorded rather than every value, so a
   protocol rewording does not churn the file while a key rename, reorder or removal still
   fails. Both live in `tests/test_golden_report.py` against `tests/data/`.
7. Static typing and linting in CI across supported Python versions. *No CI exists yet, so this
   step is a manual convention; the real-corpus tests skip themselves when the corpus is absent,
   which means a quarter of the suite runs only where someone has fetched it.*

## Implementation roadmap

1. **Foundation (done):** packaging, domain types, typed V1 protocol declarations, report model,
   separation tests, and project documentation.
2. **Evidence kernel (done):** evidence inventory with referential integrity, requirement matcher
   honouring gates, dependencies and alternative groups, aggregation rules, trace graph, and
   structured JSON serialization. The engine now contains no requirement or rule identifiers.
3. **Parsing boundary (done):** parser contract, `ParseDiagnostics` carrying real
   `UnavailableReason` values, ORCA extraction hardened against real output from 2.6 to 5.0, and
   the vendored-free fixture path.
4. **Status correctness (done):** derived keys inherit their sources' absence reason, a
   non-terminating file withholds list observations, an unexamined scope reports `UNKNOWN`, and
   the parser-to-audit path is covered end to end against the real corpus.
5. **Scientific validators (in progress):** convergence, Hessian order and method consistency are
   in place for the three families. What remains is the parser's own fidelity — table selection
   and per-job block boundaries (D-27 to D-29) — which currently limits what those validators can
   be trusted to see.
6. **CLI and reports (next):** a free-text question, stable machine-readable output with a golden
   report, a text renderer with snapshots, an exit-code policy, `examples/`, and end-to-end tests
   over the CLI. Blocked on decisions Q13 and Q14.
7. **Adapter seam:** structured import for external hole-electron/NTO/SOC/IRC analyses, initially
   targeting documented Multiwfn-exported data without reimplementing its algorithms. Until this
   exists, most accepted evidence types have no producer, so `SUPPORTED` is reachable only
   through a user assertion, which is capped at `WEAK`/`INDIRECT` and therefore cannot satisfy the
   requirements that demand more.
