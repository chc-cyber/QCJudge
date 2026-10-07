# Changelog

All notable changes will be documented here. This project follows Semantic Versioning once its
public API stabilizes.

## Unreleased

### Foundation

- Foundational package and immutable typed domain model.
- Versioned schemas for CT excitation, TADF potential, and transition-state validation.
- Independent execution-validity and evidence-adequacy report axes.
- Initial architecture, scope, contribution, citation, and licensing documents.
- `docs/v0.1-plan.md`: workflow, module map, debt register, acceptance corpus, and milestone gates.
- `docs/benchmarks.md`: benchmark layers, sourced and licence-audited data origins, ablation labelling, and evaluation metrics.

### Evidence kernel

- Three-level reasoning chain: question, hypothesis, claim, evidence requirement.
- Registered `FactKey`, `EvidenceType`, `EvidenceOrigin`, and `RequirementRole` vocabularies
  replacing free strings.
- `EvidenceInventory` with referential integrity; every fact and evidence item carries provenance.
- `EvidenceGroup(ANY_ONE|ALL)` making alternative evidence structural rather than reciprocal.
- Validator registry resolving protocol rules by `implementation_key`, failing loudly on an
  unimplemented rule instead of skipping the check.
- Requirement classification by `gating_rules` (unusable inputs) versus `contradicting_rules`
  (evidence that rules the requirement out), plus a third `STRUCTURE` validation scope so a
  converged minimum is not reported as a failed calculation.
- Aggregation with prerequisite and substantive roles, an explicit status precedence, and a
  trace graph reaching from the question back to the source file.
- Stable JSON report schema `qcjudge.audit_report/1`.
- An acceptance corpus of 18 cases proving that technical success does not imply scientific
  sufficiency, and a layering test that parses every source file to enforce the dependency
  direction and the ban on LLM, web, and numeric dependencies in the core.

### Parser boundary

- Parsers now emit `Observation`s with line locations and `ParseDiagnostics` carrying a real
  `UnavailableReason` per unsupported or missing value, replacing the parallel
  `CalculationRecord` whose typed fields carried no provenance. Removing it closed the dual
  representation the evidence kernel had inherited.
- ORCA extraction validated against real output from ORCA 2.6 through 5.0 rather than only
  against fixtures, which corrected five defects: a padded charge line, a dot leader, an
  `au`-then-`eV` excited-state format, a convergence message ORCA 5.0 wraps across two lines,
  and repeated keywords in a multi-job file misreported as ambiguity.
- Basis set is read from ORCA's own "utilizes the basis" line, and charge and multiplicity
  fall back to the `* xyz` input echo when the printed system block is absent.
- Singlet and triplet manifolds are read into separate keys, so a singlet-triplet gap can no
  longer be assembled from a merged list of excitation energies.
- Evidence strength is now declared by the protocol via `EvidenceDerivation` and applied by
  `evidence/derivation.py`, instead of being assigned in extraction code.
- `tools/fetch_benchmark_data.py` and a pinned `tools/benchmark_manifest.json` fetch real
  output on demand with SHA-256 verification. Nothing third-party is committed.
- `tests/test_real_orca_output.py` runs the parser over a pinned `cclib-data` subset, and is
  skipped until the corpus has been fetched.

### Fixed

- `tests/golden.py` wrote its fixture file without creating its directory first, so the two
  golden tests that build two reports from subdirectories passed only because `tmp_path` already
  existed. Running the whole suite in one process exposed it; the builder now creates the
  directory. The golden shape and both text snapshots were unchanged by the fix.
- The ORCA stub's excited-state pattern required the oscillator strength to abut `f=`, which
  ORCA pads with spaces, so every excited state was silently lost. Found by running the CLI.
- An unknown requirement dependency was reported as a dependency cycle.
- A derived fact was both produced and declared unavailable, which the inventory rightly
  rejected. Found by running the CLI against a real file.
- A claim carrying only recommended evidence was reported as unassessable, which then let the
  hypothesis level contradict the overall status within a single report.

### Status correctness (parser to audit)

Found by driving real ORCA output through the whole chain rather than through hand-built
inventories, which is what the acceptance corpus does and why it could not see any of this.

- A key produced only by arithmetic reported `UNSUPPORTED_CONSTRUCT` when its sources had simply
  never been computed. A complete, converged optimization with no frequency job was therefore
  reported `NOT_ASSESSABLE` — our reader blamed for the researcher's omission — where the plan
  promises `INSUFFICIENT`. Derived keys now inherit the reason recorded for their sources, and an
  access failure among the sources still outranks a coverage gap. `ORCA4.1/dvb_gopt.out` is the
  real file that shows it.
- A list-valued observation from a file that did not end normally was still projected, so a
  truncated Hessian yielded a mode count: a partial list of all-positive modes produced
  `CONTRADICTED`, fabricating a refutation from an unreadable file. Such observations are now
  withheld and recorded as `FILE_TRUNCATED`, which also makes true the "the parser refuses to
  report a count from a file that did not end normally" claim in `validators/execution.py`.
- `methodology_status` returned `PASS` when a protocol declared no methodology check at all, so
  an unexamined axis was indistinguishable from an examined one. It now reports `UNKNOWN`, and
  the text renderer states that no check was declared instead of omitting the section.
- `ts.pathway_connection` was both a claim id and a requirement id, so the trace carried a
  self-referential edge. The claim is renamed and a protocol now refuses any id shared across
  the hypothesis, claim, requirement and rule namespaces.
- The report carried the protocol version but none of its declared `limitations`,
  `background` interpretations or `max_defensible_claim_strength`, so a reader could not see what
  the protocol refuses to establish. All three now reach the report, the JSON contract and the
  text renderer.
- `insufficiency_conditions` was declared on six requirements and read by nothing, so the
  protocol's own account of what a requirement accepts never reached a reader: `ts.mode_identity`
  reported "no evidence of an accepted type was supplied" when the actual gap was that the
  imaginary frequency was known and its mode was never inspected. A requirement that comes out
  `INSUFFICIENT` now restates its declared conditions in its rationale. All of them, rather than
  one: the conditions are prose, so which one a given gap matches is not machine-decidable, and
  guessing would be worse than listing.

### Added

- `tests/test_end_to_end.py` drives parse, project, derive, match and aggregate over both
  synthetic files and the real corpus, pinning all of the above.
- `tests/test_fetch_benchmark_data.py` pins the manifest rules the fetch script enforces.
- `tests/test_cli.py` covers the exit-code policy and both researcher-input channels.
- `tests/test_golden_report.py` with `tests/data/`: the JSON report's structure is pinned as a
  golden file, and both text renderings are pinned byte for byte, so a change to the contract or
  to what a reader sees has to be deliberate. The shape is recorded rather than every value, so a
  protocol rewording does not churn it. `render/text.py` had no test at all before this, which is
  the module standing between the structure and "explanation overshoot".
- `tests/golden.py` builds the fixed report both use, including a frozen provenance stamp --
  without it a parser's clock reading would make byte comparison impossible. It can regenerate
  the golden files deliberately (`python tests/golden.py`).
- `tests/conftest.py` accepts `QCJUDGE_TEST_SCRATCH` to route `tmp_path` somewhere writable, for
  environments that cannot list pytest's own directory under the system temporary root. Without
  the variable nothing changes. With it the whole suite runs in one process, which is how the
  defect below was found.
- `examples/`: three worked ORCA jobs with the command, the full report and the reasoning,
  chosen to make one point each -- one imaginary frequency is not a pathway
  (`PARTIALLY_SUPPORTED`), a converged minimum is not a saddle point (`CONTRADICTED` with
  execution `PASS`), and a small singlet-triplet gap is not a RISC channel
  (`PARTIALLY_SUPPORTED`, capped by design). `tests/test_examples.py` pins every documented
  verdict, so a change that silently turns an example into a different result fails the suite
  rather than making the documentation wrong.
- `.github/workflows/ci.yml`: ruff, mypy and pytest across Python 3.12 and 3.13 on Linux, macOS
  and Windows, with the real ORCA corpus fetched as an optional step that cannot fail the build.
  Python 3.13 is now also declared in the classifiers.
- `.gitattributes`: LF normalisation, with `tests/data/` marked `-text` because those fixtures are
  compared byte for byte.
- `tests/test_ci_configuration.py` holds the workflow to its own claims: the interpreter matrix
  must agree with the classifiers and `requires-python` in `pyproject.toml`, in both directions.
  It caught that 3.13 was tested but not declared before the workflow ever ran.

### Adapter seam

- **The adapter seam** (`src/qcjudge/adapters/`, `docs/adapter-format.md`). The analyses that
  decide most real questions -- hole-electron descriptors, NTO composition, spin-orbit couplings --
  are computed by tools QCJudge deliberately does not reimplement, so they are imported instead.
  One documented JSON format, one reader, no heuristics: every value names a registered fact key
  and states its unit, and anything else is refused with the offending name. Imported values keep
  a producer of their own, and evidence derived from them carries `origin: adapter`, so the report
  distinguishes a number the calculation emitted from one an external tool supplied. Reached from
  the CLI as `--analysis FILE`. This is what makes a full `SUPPORTED` verdict reachable: a TADF
  audit finds the gap itself and needs the imported coupling for the RISC channel.
- `ExtractedFact` and `ParseResult` now carry an explicit `origin`, and a derivation inherits it
  from its source facts rather than assuming `PARSED`. Inferring it from a producer name was tried
  first and abandoned: it misattributed the test fixtures, which are parsed facts from a producer
  that matches no naming pattern. The projection knows which reader produced a result, so it says.
- `ParseResult.calculation_id` lets a reader name the calculation its values describe. An adapter
  export covers several calculations, and each becomes its own result so one calculation's
  descriptor cannot answer a claim about another.
- `tests/test_adapter.py`: 25 tests, most of them about refusal -- a wrong unit, a missing unit, an
  unregistered quantity, a registered-but-unsupported quantity, a missing producer, a wrong format
  version, no calculations, and invalid JSON -- plus the ones that matter most: every family now
  reaches `SUPPORTED`, a mixed audit keeps the two provenances apart, and IRC evidence reaches a
  saddle through the protocol's declared `ANY_ONE` group while saying it happened that way.
- A refused import names the quantities the seam does carry. An export is written by hand or by a
  small conversion script, so the useful thing to say is what it should have written rather than
  only that it was wrong. The list is generated from the same set the reader enforces, so it
  cannot drift from it.
- **`irc.connects_two_minima`** closes the last family. TS pathway evidence had no source at all,
  so `ts.pathway_connection` could never be met. The fact records the weakest thing an IRC run
  establishes -- the path descended to two distinct minima -- and is declared `MODERATE`, because
  reaching two minima is not the same as reaching the intended ones. That distinction is the
  researcher's question, and the protocol does not answer it for them.

### Command line

- **`--ask TEXT` records the question in the researcher's own words.** The report previously
  stated the protocol's own hypothesis where the question belongs, so the audit of "is this a
  TADF emitter?" was presented as an audit of whatever the protocol asserted. Without `--ask`
  the hypothesis is still used as a fallback to keep the field populated, but an empty `--ask`
  is refused rather than silently becoming that fallback.
- **`--analysis FILE`** imports an external analysis, such as a hole-electron or spin-orbit
  export. Its values are attributed to the tool that produced them, not to the calculation. A
  malformed import exits `2` rather than producing an audit from partial data.
- **Documented exit-code policy.** An exit code describes the run, not the verdict: `0`
  whenever an audit was produced and printed, including one whose evidence is insufficient,
  because the report is the deliverable. `2` means no audit could be produced. A caller that
  needs the finding reads `evidence.overall_status` from `--format json`. Previously every
  failure path returned `2` and the verdict never appeared in the code at all.
- **`--condition KEY=VALUE`** reports something only the researcher can observe, such as the
  donor/acceptor partition they chose. A protocol may name a key with `expert_review_when_key`
  to have an expert boundary tested rather than guessed; a key no protocol names is still
  recorded, so the report shows what the audit was told.
- **`--expert-review REQUIREMENT_ID`** states that a declared expert boundary has been reached.
  Both channels refuse an unknown requirement, or one that declares no boundary, so a typo
  cannot look like a recorded judgement. Four `expert_review_when` declarations that nothing
  read now fire; a boundary is only reachable once the requirement's premise is established, so
  a missing calculation stays a coverage gap rather than becoming a question for a human.

### Parser correctness

Reading ORCA's tables was wrong in several independent ways, each silent, and each found by
reading the real output already on disk rather than the fixtures.

**Absorption spectrum (oscillator strengths).**

- The table was located by a bare substring that also matches `SPIN ORBIT CORRECTED ABSORPTION
  SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS` and `SOC CORRECTED ... MOMENTS*`, so an
  ORCA 5.0 file could be read from a corrected table. The header now matches a whole line, a
  corrected table is never substituted for the plain one, and its presence is reported.
- The oscillator strength was taken as the fourth whitespace field. The SOC-corrected tables
  use a wider state prefix, so that field holds the wavelength: a real 5.0 table yielded
  `462.1, 330.0, ...` as oscillator strengths under a clean `complete` outcome. The strength is
  now read from the field the table's own `fosc` heading names.
- The table ends with a separator line and also *begins* its rows after one, so treating a
  separator as the end of the table read nothing at all. Every electric-dipole table in the
  ORCA 2.9, 4.0 and 4.2 corpus returned no strengths.
- A row the pattern could not read, such as ORCA's `spin forbidden (mult=3)`, ended the table
  and dropped every state after it. Such rows are now skipped.

**Vibrational frequencies.**

- The vibrational frequency table was collected across the whole file, so a file holding two
  jobs merged their Hessians into one mode list. Two jobs with one imaginary mode each were
  counted as two, and since that count feeds a *contradicting* rule the audit reported the
  requirement as `CONTRADICTED` -- a refutation manufactured from an arithmetic mistake. Each
  block is now scoped by its own header, only the first is read, and the rest are reported. A
  block appearing after the last termination marker belongs to a job that did not finish, so it
  is not read at all.

### Known issues

- **No git repository exists yet.** Git is not installed in the authoring environment, so the
  initial commit and the workflow's first run have to happen elsewhere. `.gitignore`, the
  workflow and the tests that check it are all in place.
- `ruff format` is deliberately not a gate. Formatting was never adopted and the tree is a mix of
  styles, so a format check would fail on arrival rather than guard anything. D-33 records this
  as a decision; `tests/test_ci_configuration.py` fails if a format gate is added without
  formatting the tree in the same change.
- `tests/data/` holds files compared byte for byte, so `.gitattributes` pins the tree to LF and
  marks that directory `-text`. Without it a Windows checkout with `core.autocrlf=true` would
  fail the golden text tests on a clean clone, and the failure would look like a rendering
  regression rather than a checkout setting.

### Tooling

- `tools/fetch_benchmark_data.py --verify` reported `ok` and exited 0 for a file the manifest
  did not describe, so an unverified file was indistinguishable from a verified one, and
  `--update-manifest` would have pinned it. The manifest key set must now match the fetched set
  in both directions, `--update-manifest` refuses to write while anything failed, a mismatch is
  detected before the bytes are written instead of after, timeouts and short reads are caught
  rather than crashing, and a pinned commit is no longer re-resolved. Covered by
  `tests/test_fetch_benchmark_data.py`.

