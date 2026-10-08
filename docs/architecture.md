# V0.1 architecture

## Decision

QCJudge uses a layered, dependency-light Python package with an immutable domain core.
Protocol V1 declarations are typed Python data, not YAML. Python provides construction-time
validation, safe refactoring, and direct testability without a runtime schema dependency.
Serialization can be added at the boundary later without making serialized data authoritative.

The intended dependency direction is:

```text
CLI -> parsers / adapters -> fact projection -> audit engine
                                        -> domain + protocols + validators
                                        -> target selection / evidence matching -> renderers
```

Parsers produce provenance-bearing observations. They do not assess claims. Validators make
bounded, deterministic checks. The audit engine maps evidence to protocol requirements and
preserves the trace from question through claims, requirements, facts, and assessments.

## Core model

- `ResearchQuestion` selects one supported family, states hypotheses and binds protocol claims.
- `ExtractedFact` is an observation or computed value with provenance; `None` represents unknown.
- `Hypothesis` groups the claims that make a broad proposition checkable, so a report can say
  "claim A supported, claim B unevidenced, therefore the hypothesis is not established".
- `Evidence` cites facts and records strength, directness, and origin.
- `EvidenceRequirement` belongs to a claim and declares necessity, role (substantive or
  prerequisite), accepted evidence types, minimum strength and directness, required facts,
  dependencies, group membership, target-association requirements, gating and contradicting rules,
  and expert-review boundaries.
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
  report alone. It also preserves all researcher inputs, selected calculation IDs and association
  diagnostics while retaining the full supplied inventory. It aggregates the axes without a score.

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
and `adapters/` all exist and carry working behaviour. The JSON analysis seam is implemented.
`evidence/selection.py` restricts scientific matching and validators to one root calculation and
its explicitly linked analyses; ambiguous association blocks requirements instead of joining
unrelated evidence. Derivations can declare fact-value predicates, so presence does not imply
a positive outcome. The milestone order and remaining coverage gaps are tracked in
[docs/v0.1-plan.md](v0.1-plan.md).

Every module that leaves the package ships with the tests that hold it in place. Two boundaries
have proved easy to test on one side only and therefore worth calling out:

- **parser to audit.** Testing the engine against hand-built inventories proves the reasoning;
  it cannot show what status a real file produces. `tests/test_end_to_end.py` crosses the
  boundary on the real corpus for exactly this reason.
- **declaration to behaviour.** A field a protocol declares but nothing reads is worse than a
  missing field, because the declaration reads as an implemented control. `expert_review_when`
  was a repaired example (D-31). Presence-only IRC derivation and missing target association
  were later repaired with consumed predicates and an association gate (D-34/D-35).

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
- **Stringly typed evidence:** fact and evidence names are registered enums. Preserve this
  refusal boundary before third-party protocols are supported.
- **Unrelated evidence:** a result retains its own ID and source link. Multiple independent roots
  require explicit target selection; state/molecule conflicts cannot establish a claim.
- **Cross-job contamination:** the ORCA parser scopes all observations to the first identifiable
  execution; ambiguous compound boundaries withhold scientific observations.
- **Alternative/dependency semantics:** complex Boolean evidence graphs can become opaque. Keep V1
  semantics narrow and add graph/cycle validation before the audit engine consumes them.
- **Overconfident prose:** rendering can exceed structured conclusions. Generate templates from the
  audit state and test that explanations preserve status and uncertainty.
- **Fixture realism:** synthetic outputs may miss vendor quirks. Add licensed/redacted real-world
  fixtures and parser fuzz/regression tests incrementally.

## Minimal dependencies

The runtime core uses only the Python standard library. Development extras are pytest, Ruff,
mypy and Hypothesis; Hatchling builds the package. A later ORCA parser adapter may optionally depend
on cclib after
its capability and license are reviewed. CLI parsing uses `argparse`; richer UI
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
7. Static typing, linting and tests are defined in CI across Python 3.12/3.13 and three operating
   systems. The first actual GitHub matrix passed all seven jobs on 2026-10-08, with the real
   corpus and independently installed wheel checked in all six test jobs.
8. Target-association, invalid quantity and multi-job end-to-end regressions cover the repaired
   false-SUPPORTED cases. Real-corpus tests remain optional when data cannot be fetched.

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
5. **CLI and reports (done):** free-text questions, documented exit codes, stable structured
   output, golden reports, four examples and tested researcher input channels.
6. **Adapter seam (done):** attributed JSON import of hole-electron/NTO/SOC/IRC facts; explicit
   source association and quantity validation. No external analysis algorithm is reimplemented.
7. **Hardening (in progress):** all three built-in protocols are 1.1.1, closing invalid-value
   false-SUPPORTED paths;
   report schema 2 records scope and researcher inputs. Facts reject nonfinite numbers and
   duplicate calculation/key pairs. Hypothesis tests exercise target graphs, values and ordering;
   local audit bundles preserve raw inputs and compare replays. Actual remote CI is verified;
   independent expert cases and compatibility across released versions remain release work.
   LLM stays deferred.
