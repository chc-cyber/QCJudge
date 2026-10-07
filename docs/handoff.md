# QCJudge — agent handoff

Updated 2026-10-07 after the M5 hardening pass. M0-M4 are complete; M5 is in progress.
The local measurements below include the real ORCA corpus. Where the plan and this file disagree,
use this file's latest measurement and correct the plan.

Read `docs/v0.1-plan.md` for the debt register and milestone gates, `docs/architecture.md` for the
durable architecture, and this file for "where it actually is right now and what will bite you".

---

## 1. What the project is

QCJudge is an **evidence auditor** for computational chemistry. It answers one question: given a
stated scientific question, do the available computational results constitute appropriate and
sufficient evidence for it?

It does **not** answer "did the job run" and it does **not** answer "is the conclusion true".

Explicit non-goals, normative rather than descriptive: no workflow planning or autonomous agents, no
execution or HPC orchestration, no input generation, no wavefunction-analysis algorithms
(Multiwfn and peers are *consumed*, never reimplemented), no retrospective reproducibility
benchmarking, no scalar score, no web frontend, no database.

V0.1 covers exactly three question families and refuses to widen until those are architecturally
sound:

| Family | `QuestionFamily` | Protocol id |
| --- | --- | --- |
| Charge-transfer excitation | `ct_excitation` | `charge_transfer` |
| TADF potential | `tadf_potential` | `tadf` |
| Transition-state validation | `transition_state` | `transition_state` |

## 2. The defining invariant

> **A report may be `execution = PASS` and `evidence = INSUFFICIENT` at the same time, and that is
> the normal, expected outcome for a large fraction of real audits.**

Everything else in the codebase exists to protect that separation. `tests/test_audit_separation.py`
and the acceptance corpus in `tests/test_acceptance_corpus.py` exist to hold it shut.

The sharpest consequence is the distinction between:

- `INSUFFICIENT` — a claim about **evidence coverage**: the calculation was not provided.
- `NOT_ASSESSABLE` — a claim about **epistemic access**: we could not read what was provided.

Conflating them either hides a missing calculation or blames the researcher for a gap in our own
reader. Missing-data classification follows the reader's `UnavailableReason` per fact. Explicitly
ambiguous target association or an impossible requested state index also makes a scientific
requirement `NOT_ASSESSABLE`; this is declared and tested separately from execution success.

## 3. Immutable design rules

These are enforced, not aspirational. Break one and a test fails.

1. **The deterministic core does not depend on an LLM.** Delete any LLM layer and the system stays
   scientifically usable. `tests/test_layering.py` denies LLM SDKs, web frameworks and numeric
   stacks as imports in the core.
2. **Scientific logic lives in reviewable, testable, versionable rules**, never as ID branches in
   the engine. `audit/engine.py` contains no requirement or rule identifier at all; rules resolve
   from the protocol through `validators/registry.py` by `implementation_key`.
3. **Missing is not false.** Unknown stays `UNKNOWN`; absence carries a classified reason.
4. **Every fact and evidence item carries provenance.** Source file, producer, producer version,
   location, extraction time.
5. **Evidence strength is declared by the protocol**, never assigned by a parser or an adapter
   (`EvidenceDerivation` + `evidence/derivation.py`).
6. **No scalar score.** The evidence graph stays visible and traceable.
7. **Where expert judgement is required, return `REQUIRES_EXPERT_REVIEW`** rather than pretending
   to be deterministic. That is a success condition of the design, not an error.
8. **Epistemic levels are never silently promoted**:
   `OBSERVATION / COMPUTED_FACT / METHOD_ASSUMPTION / INTERPRETATION / EVIDENCE / CLAIM`.

## 4. Architecture

### 4.1 The nine-stage workflow

Each stage has exactly one owner. This is the spine.

| # | Stage | Owner |
| --- | --- | --- |
| 1 | Research question | `domain/question.py` |
| 2 | Hypothesis | `domain/question.py` |
| 3 | Claims | `domain/question.py` + `protocols/` |
| 4 | Evidence requirements | `protocols/` |
| 5 | Available calculations | `parsers/`, `adapters/` |
| 6 | Extracted facts | `evidence/facts/projection.py` |
| 7 | Validity checks | `validators/` |
| 8 | Evidence mapping | `evidence/matching.py` |
| 9 | Sufficiency assessment | `audit/` |

Derived outputs — missing evidence, recommended next step, rendered explanation — are projections
of the stage-9 result, never new reasoning.

### 4.2 Module map (40 source files)

```
cli/main.py             argparse, target selection and exit-code policy
render/text.py          human-readable report
render/json_report.py   versioned machine-readable contract

audit/engine.py         orchestration only; no rule or requirement ids
audit/aggregation.py    requirement -> claim -> hypothesis -> overall
audit/trace.py          the inspectable why-chain

evidence/matching.py    requirements, groups, dependencies and association gate
evidence/derivation.py  facts -> evidence with protocol strengths and value predicates
evidence/selection.py   explicit calculation links and target scope
evidence/facts/projection.py  observations -> facts, absences and arithmetic

adapters/json_analysis.py   validated external-analysis import

parsers/base.py         the reader contract
parsers/orca.py         the declared ORCA subset, first identifiable execution only

validators/registry.py  implementation_key -> rule callable
validators/collect.py   fact reading + absence explanation
validators/execution.py convergence and Hessian order
validators/methodology.py consistency checks
validators/target_state.py explicit S/T index bounds, without interpreting state identity

protocols/v1.py         the three built-in protocols, currently version 1.1.0

domain/                pure types; imports nothing but stdlib + errors
```

### 4.3 Dependency direction (enforced by `tests/test_layering.py`)

Strictly inward. `domain` imports only the standard library and `qcjudge.errors`. The forbidden
matrix is explicit in the test, per first-level package. `render` may import `domain` only.

Deliberate deviation: `EvidenceInventory` lives in `domain/evidence.py` rather than
`evidence/inventory.py`, because `AuditReport` carries it and `domain` may not import `evidence`
(D-16, accepted by design).

### 4.4 Vocabularies (registered, never free strings)

- **24 `FactKey`** — all registered in `domain/evidence.py`, so an import or a parser cannot
  introduce a free string. Three groupings matter, and they are not the same axis:

  | Group | Count | Meaning |
  | --- | --- | --- |
  | Read by the ORCA parser | 15 | Observations lifted from a calculation's own output. |
  | Computed arithmetically | 3 | `frequency.observed_mode_count`, `frequency.imaginary_count`, `tddft.state_count`. These are `COMPUTED_FACT`, and `frequency.imaginary_count` is the one that feeds a *contradicting* rule — see D-23 and D-28. |
  | Carried by the adapter seam | 7 | Listed in `docs/adapter-format.md`. |

  `tddft.state_count` is in both the arithmetic and the import groups: normally the projection
  computes it by counting states, but an export may state it outright. A reader supplying a value
  the projection would otherwise compute is why projection checks `observed` as well as `derived`
  before recording an absence.
- **16 `EvidenceType`** — what a requirement accepts.
- **Three validation scopes**: `execution`, `structure`, `methodology`. They are kept apart because
  a converged *minimum* is a successful calculation that is not a saddle point.
- **Validation statuses**: `pass`, `warning`, `fail`, `unknown`, `requires_expert_review`.
- **Assessment statuses**: `supported`, `partially_supported`, `insufficient`, `contradicted`,
  `not_assessable`, `requires_expert_review`.

### 4.5 The three boundaries

**Parser / adapter boundary.** Both implement the same shape: return `ParseResult` carrying
`Observation`s plus `ParseDiagnostics` with an `UnavailableReason` for every supported key that was
not produced. A parser reads a calculation's own output; an adapter reads a documented import of an
external analysis. The distinction is carried by `ParseResult.origin` and lands on every fact as
`ExtractedFact.origin`, so derived evidence inherits it.

**Deterministic / expert / LLM boundary.** Deterministic: parsing, convergence flags, counting
modes, coverage arithmetic. Expert: mode-to-reaction-coordinate correspondence, donor/acceptor
partition choice, whether a coupling is large enough to matter, "is this method adequate". No
numeric CT or TADF cut-off is asserted anywhere; those are expert boundaries by design.

**LLM firewall (M6, not built).** The LLM surface is `str -> ResearchQuestionDraft` and
`AuditReport -> str`. It can never receive facts, validation results or assessments as writable
objects.

## 5. What is done

### 5.1 Measured state

| Check | Command | Result |
| --- | --- | --- |
| Tests | `python -m pytest -q -rs` | **548 collected: 546 passed, 2 skipped, 0 failed** |
| Types | `mypy --strict src/qcjudge` | clean, **40 files** |
| Lint | `ruff check .` | clean |
| Format | `ruff format --check` | **not a gate** — see D-33 |
| Real corpus | `python tools/fetch_benchmark_data.py --verify` | all 12 pinned files verified |
| Packaging | wheel build, independent install and isolated CLI check | `0.1.0.dev1` verified |
| Repository | local Git on `main` | baseline `22c0d25` plus this hardening change; no remote configured |

Both skips are the root-facade cases in `tests/test_layering.py`: the package root has no declared
import restrictions. The previous handoff incorrectly attributed them to missing corpus files.
All real-corpus tests run in this measurement. This is Windows/Python 3.12 validation; it is not
evidence that the full remote OS/Python matrix has passed.

Current compatibility identifiers: package `0.1.0.dev1`, report `qcjudge.audit_report/2`, built-in
protocols `1.1.0`, ORCA parser `0.4.0`, analysis adapter `0.2.0`. Schema 2 adds audit scope,
full researcher inputs and subject association fields; consumers of schema 1 need an update.

The final wheel at `.test-scratch/dist-final/qcjudge-0.1.0.dev1-py3-none-any.whl` was installed
in a fresh independent environment; `python -I tools/verify_installed_package.py` passed. All
40 packaged Python modules match the final source byte-for-byte. Wheel SHA-256:
`78303e077ac716d96804e7b565c27a345c035ead89399147096e43c6e7bdcd97`. The scratch
artifact is ignored and is not a published release.

### 5.2 Milestones

| Milestone | State |
| --- | --- |
| M0 Foundation | complete |
| M1 Evidence kernel | complete |
| M2 Parser boundary | complete |
| M2.5 End-to-end status correctness | complete |
| M3 CLI and reports | complete |
| M4 Adapter seam | complete |
| M5 Hardening and release | **in progress** — hardening and local wheel verified; remote CI, property tests, cross-version replay and tag pending |
| M6 LLM layer | not started, deferred by design |

### 5.3 Substantive defects found and closed (D-23 … D-32)

Four were severity H. The important thing for a successor is the *class* of defect, because the
same class will recur:

**Status semantics** — the answer a user receives was wrong even though every unit test passed:

- A key produced only by arithmetic reported `UNSUPPORTED_CONSTRUCT` when its sources were simply
  never computed. A complete, converged optimization with no frequency job therefore came out
  `NOT_ASSESSABLE` — our reader blamed for the researcher's omission — where the plan promised
  `INSUFFICIENT`. Derived keys now inherit their source's reason.
- A list-valued observation from a file that did not end normally was still projected, so a
  truncated Hessian yielded a mode count, and a partial list of all-positive modes fabricated
  `CONTRADICTED`. Truncated files now withhold list observations.
- `methodology_status` returned `PASS` when the protocol declared no methodology check at all. It
  now returns `UNKNOWN`, and the text renderer says so.

**Parser fidelity** — silent, and capable of inventing numbers:

- The absorption-spectrum table was located by a bare substring that also matches
  `SPIN ORBIT CORRECTED …` and `SOC CORRECTED … *`, and its row pattern read the fourth column
  blindly. A five-column row yields the **wavelength** where the oscillator strength belongs. Worse,
  every real TD file read as **no strengths at all**, because the reader treated the separator line
  after the heading as the end of the table. Fixed by whole-line header matching, excluding
  corrected tables, locating the column by the `fosc` heading field, and ending the table on
  consecutive unreadable rows.
- The vibrational frequency block was collected across the whole file, so a two-job file merged
  Hessians. Two jobs with one imaginary mode each were counted as two, and because that count feeds
  a *contradicting* rule the requirement became `CONTRADICTED` — a refutation manufactured from an
  arithmetic mistake. Each block is now scoped by its own header; only the first is read and the
  rest are reported; a block after the last termination marker is not read at all.

**Tools** — `fetch_benchmark_data.py --verify` reported `ok` and exited 0 for a file the manifest
did not describe, so an unverified file was indistinguishable from a verified one, and
`--update-manifest` would have pinned it. It also wrote before verifying.

**Declared but unread protocol fields** — `expert_review_when` (four expert boundaries that never
fired), `max_defensible_claim_strength`, `limitations`, `background`, and eleven
`insufficiency_conditions` across six requirements. All are now consumed.

The 2026-10-07 hardening closes D-34 through D-40 (see the plan for the register):

- False IRC, zero excitation count and zero SOC are retained as facts without becoming positive
  evidence. These are protocol-declared predicates, not engine branches or universal size cutoffs.
- Every result has a distinct calculation ID. Analyses attach through `source_calculation_id`;
  reusing a calculation ID is rejected. Multiple independent roots require `--target` or
  `--context calculation_id=...`. The selector includes explicit descendants and refuses missing
  parents, cycles, or conflicting molecule/state metadata. Missing optional labels are not guessed.
  Link-graph consistency is checked before selection, so an invalid unrelated link is still refused.
- Selected evidence alone drives validation and matching; the report retains the full inventory.
  An unlinked analysis cannot silently support a parsed calculation.
- All ORCA facts are scoped to the first identifiable execution, including completion markers,
  method, charge, multiplicity, SCF, frequencies and excited-state lists. Ambiguous compound input
  with no reliable boundary withholds scientific observations rather than combining jobs.
- Imported quantities have per-key types, finite values, exact units and domain bounds. Zero count
  remains a valid fact; booleans cannot bypass numerical validation or unit checks.
- CT rejects explicit impossible S/T indices. Positive total counts give only a necessary upper
  bound and never assign spin character. An explicitly empty target manifold cannot be rescued
  by a positive total count; zero/empty sources without positive assignment remain coverage gaps.
  D-21 remains: choosing the scientifically relevant state needs more than an index check.
- Schema 2 records every supplied researcher condition, expert flag and association field, including
  inputs not consumed by a rule. This does not yet implement raw-input/checksum replay.
- The CI strategy now uses a legal direct matrix; each test job builds and independently checks a
  wheel. These steps are verified locally, while the actual remote matrix remains pending.

### 5.4 Evidence coverage — measured, and the key number for a successor

**9 of 16 accepted evidence types still have no producer.** This is the single most useful measure
of how far the three families are from being fully answerable.

| Family | Derivable today | No producer yet |
| --- | --- | --- |
| `charge_transfer` | `excited_state_assignment`, `hole_electron_analysis`, `nto_analysis` | `attachment_detachment_density`, `method_comparison`, `range_separation_validation` |
| `tadf` | `singlet_triplet_gap`, `spin_orbit_coupling` | `oscillator_strength`, `radiative_rate`, `risc_rate`, `vibronic_coupling_analysis` |
| `transition_state` | `optimization_and_frequency`, `irc` | `normal_mode_inspection`, `reaction_path_following` |

`normal_mode_inspection` is deliberately unproduced: mode correspondence is an expert boundary, and
`--expert-review` / `--condition` are the honest way to supply it.

**All three families can now reach `SUPPORTED`**, which none could before M4. Each needs a value
from an external analysis, because the analyses that decide these questions are the ones QCJudge
declines to reimplement.

### 5.5 The adapter seam (M4)

`src/qcjudge/adapters/json_analysis.py`, format specified in `docs/adapter-format.md`, reached as
`qcjudge audit --analysis FILE`.

Seven quantities may be imported: `scf.converged`, `tddft.state_count`,
`hole_electron.d_index_angstrom`, `hole_electron.sr_index`, `nto.dominant_pair_contribution`,
`spin_orbit.coupling_cm1`, `irc.connects_two_minima`.

Design rules that must not be relaxed:

- A quantity must be a registered `FactKey` **and** one this seam carries. A typo is refused with
  the offending name *and the list of what is accepted*.
- Every value states its unit. Only exact equivalences are converted (bohr→angstrom,
  cm-1 variants); anything else is refused, because a value in the wrong unit looks like an answer.
- A boolean stays a boolean. Flattening a convergence flag to `1.0` silently turns `PASS` into
  `UNKNOWN` — that bug was made and caught in this session.
- The importer never chooses evidence strength.
- A producer and version are required. An unattributable number does not enter the audit.

Licence position: Multiwfn is not OSI-approved. The adapter consumes exported text and never
bundles or links it.

### 5.6 Test suite

By purpose, in the order they are worth reading:

| File | Why it exists |
| --- | --- |
| `test_acceptance_corpus.py` | Scenario matrix: technical success is independent of scientific sufficiency. |
| `test_audit_separation.py` | The independence property as examples. |
| `test_layering.py` | Import-boundary matrix over the source tree. |
| `test_real_orca_output.py` | Real ORCA 2.6-5.0 outputs from the pinned corpus. |
| `test_orca_parser.py`, `test_orca_job_boundaries.py` | Reader contract and complete/truncated/compound job isolation. |
| `test_end_to_end.py` | Parser-to-audit boundary. |
| `test_adapter.py` | External import types, units, bounds and provenance. |
| `test_target_association.py` | Actual pipeline target links, ambiguity, metadata and CLI selection. |
| `test_fact_predicates.py` | False IRC, zero states and signed/nonzero SOC through actual audits. |
| `test_target_state.py` | Impossible indices, manifold bounds and zero-source coverage gaps. |
| `test_protocols.py`, `test_inventory.py`, `test_derivation.py` | Domain/protocol integrity and declared strengths. |
| `test_cli.py`, `test_golden_report.py`, `test_examples.py` | CLI policy, report schema and documented examples. |
| `test_insufficiency_conditions.py` | D-32's report behaviour. |
| `test_ci_configuration.py` | Actual matrix values and wheel-check commands/order. |
| `test_fetch_benchmark_data.py` | Manifest refusal rules. |

Support modules: `tests/support.py` (hand-built inventories), `tests/golden.py` (the one
deterministic report), `tests/conftest.py` (scratch routing, §6.2).

---

## 6. Current difficulties

### 6.1 PENDING EXTERNAL INPUT — actual remote CI (D-13)

Git 2.53.0 is installed and the local repository is initialized on `main`. The pre-hardening
M4 baseline is commit `22c0d25`; this hardening is recorded separately. There is no configured
remote. A GitHub repository URL is needed before publishing this checkout and running Actions.
The user was asked for that destination while local work continued.

Ready locally:

- `.gitignore` excludes the venv, corpus, test/build scratch, caches and local `.workbuddy` memory.
- `.gitattributes` normalizes LF and preserves byte-for-byte fixtures with `tests/data/** -text`.
- `.github/workflows/ci.yml` checks lint/types and tests Python 3.12/3.13 on Linux/macOS/Windows.
  Every test job also builds a wheel, replaces the editable installation from that local wheel,
  and runs `python -I tools/verify_installed_package.py` against the real CLI example.
- Real corpus fetch is optional (`continue-on-error`); unavailable network means corpus tests skip.
  A green build without the corpus is weaker than a run that includes it.

**Configuration tests and a local wheel check are not a green remote matrix.** After the intended
repository is supplied, configure its remote, push `main`, inspect the actual Actions run and fix
any OS/Python-specific failures. Do not tag `v0.1.0` merely because the local run passed.

The local sandbox created `.git` under a different Windows owner. Host Git required the exact
`E:/QCJudge` path in `safe.directory`; no wildcard trust or global author identity was configured.
Commits in this session use per-command `Codex <codex@localhost>` attribution.

### 6.2 The sandbox could not list pytest's temporary directory

In the authoring environment every `tmp_path` test failed at setup with `PermissionError [WinError
5]` because the process could not list the directory pytest creates under the system temporary
root. 72 tests were affected.

**Resolution shipped:** `tests/conftest.py` reads `QCJUDGE_TEST_SCRATCH` and routes `tmp_path` to a
writable directory. Without the variable, behaviour is unchanged.

```console
QCJUDGE_TEST_SCRATCH=/some/writable/dir pytest
```

**Why this matters more than it looks.** Until it existed, the whole suite had never run in a single
process, only in pieces with assertions replicated by hand. Running it whole immediately found a
real defect: `tests/golden.py` wrote its fixture without creating the directory, and two golden
tests had been passing only because `tmp_path` already existed.

**If you are in a normal environment, ignore this — but if some tests error at setup, this is why.**

### 6.3 `ruff format` is not a gate, deliberately (D-33)

`ruff format --check` reports work across 33 files: the tree is a mix of styles because formatting
was never adopted. An attempt to adopt it in this session failed — the sandbox denied every write
ruff attempted, even with elevated permissions — and hand-transcribing ~43 KB of formatting diff
was rejected as too likely to silently alter code.

**Decision: not a gate.** `ruff check` is enforced; formatting is not, and the workflow says so in a
comment rather than running a check that would fail on arrival.
`tests/test_ci_configuration.py::test_the_workflow_does_not_gate_on_formatting` fails if a format
gate is added without formatting the tree in the same change.

### 6.4 External volumes and network

- `tools/fetch_benchmark_data.py` needs network access to fetch the corpus, and its `--verify` needs
  the corpus present. It is pinned to a commit with SHA-256 checksums in
  `tools/benchmark_manifest.json`; nothing third-party is committed.
- `mypy` and `ruff` need writable cache directories. Redirect them if the defaults are not writable:
  `MYPY_CACHE_DIR`, and `ruff check --no-cache`.

---

## 7. The lesson that matters most for a successor

Three of the worst defects in this project shared one cause, and it is easy to reintroduce:

> **The acceptance corpus builds its inventories by hand, so no test crossed the parser boundary.**

The corpus proved the *reasoning engine* correct across 20 scenarios while the status a user
actually receives was wrong. The real corpus file that exposes it —
`ORCA4.1/dvb_gopt.out`, complete, converged, no frequency job — was already on disk the whole time.

A related and sharper version of the same trap: the field `insufficiency_conditions` was declared
on six requirements and read by nothing. **A declaration that nothing consumes is worse than a
missing one, because it reads as an implemented control.**

Consequences to keep:

- `tests/test_end_to_end.py` now drives parse → project → derive → match → aggregate over both
  synthetic files and the real corpus. Any new capability needs a test on that path, not only a
  unit test.
- `tests/test_examples.py` pins the verdict each example documents, so a change that silently
  changes an example's result fails the suite instead of making the documentation wrong.
- When adding a protocol field, add the reader in the same change, or do not add the field.

Two smaller lessons, both paid for:

- **Inferring provenance from a producer name is fragile.** It was tried and immediately
  misattributed the test fixtures. The projection knows which reader produced a result, so
  `ExtractedFact.origin` is explicit.
- **Verification by replication is weaker than running the suite.** It was necessary under the
  sandbox, and it hid the golden-fixture defect until the suite ran whole.

---

## 8. What remains

Ordered by value, with the honest reason for each.

### 8.1 Release work, in recommended order

1. **D-13: run actual remote CI.** Obtain the intended GitHub destination, push the existing local
   history, and inspect all six OS/Python test combinations plus lint/types and installed-wheel
   checks. Record whether the real corpus was available.
2. **Generative property tests.** Exercise association graphs, fact predicates, absence projection
   and aggregation; preserve execution/evidence independence and prohibit cross-root support.
3. **Replay contract.** Record raw input checksums and all audit arguments, then verify a saved
   report can be replayed by a later version. Schema 2's researcher inputs are necessary but not
   sufficient for this gate.
4. **Broader expert-labelled cases.** Add redacted real examples covering failed IRC, state identity,
   mixed jobs and weak/zero coupling; keep labels and scientific assumptions reviewable.
5. **Release review and `v0.1.0` tag.** Check dependency/attribution documentation, schema migration
   guidance and every M5 gate. Keep the current `0.1.0.dev1` designation until they pass.

### 8.2 Accepted documentation/design debt

- **D-33: formatting.** Currently excluded from gates. Adopt it only with a complete formatting
  change and the matching CI policy update.
- **D-32 residual: machine-readable "provided but not inspected".** `ts.mode_identity` has no
  `required_facts`, so this distinction is prose rather than a machine-readable predicate.

### 8.3 Optional scientific scope

- `risc_rate`, `vibronic_coupling_analysis`, `reaction_path_following` and
  `attachment_detachment_density` each need a reviewable new fact contract.
- `method_comparison` and `range_separation_validation` need a decision about whether an assertion
  about a calculation belongs in the same import seam as a recorded analysis.
- Numerical D/Sr presence is not a universal CT-character threshold. Keep state interpretation and
  the adequacy of a nonzero SOC as explicit scientific limitations rather than inventing cutoffs.

### 8.4 Deliberately not started

**M6 LLM layer**, shipped as an optional extra the core never imports. Gate: removing the extra
leaves the entire test suite green. Continue M5 before expanding to this layer.

### 8.5 Open debt carried deliberately (D-19 … D-22)

| ID | Sev | Note |
| --- | --- | --- |
| D-19 | L | Claims bind through string templates, so an under-specified question fails at audit time rather than question construction. Fails loudly and names the missing keys; acceptable for V0.1. |
| D-20 | M | Deliberate first-job subset: a multi-job file contributes only its first identifiable execution. All scientific observations and completion checks now share that scope (D-36); later jobs need a separate input rather than being merged. |
| D-21 | M | Which states are "the relevant S1 and T1" is a claim-level question the derivation does not answer. Asserting the lowest singlet and triplet would be a judgement. |
| D-22 | L | `FREQUENCY_EXPECTED_MODE_COUNT` is never produced, because 3N-6 needs an atom count and a linearity determination the parser does not make. Mode-list completeness therefore rests on the file-level truncation check alone. |

---

## 9. Conventions

- **Python ≥ 3.12**, src layout, `pyproject.toml` with hatchling, frozen slotted dataclasses, full
  type annotations, `pytest` + `ruff` + `mypy --strict`.
- **Runtime dependencies: none.** The core uses only the standard library. `cclib` is a planned
  optional extra; `numpy`/`pandas`/`pydantic`/`rdkit`/LLM SDKs/web frameworks are deliberately
  excluded.
- **Protocols are semantically versioned**; every report records the version it used. A protocol
  change that alters an audit outcome requires a version bump and a short scientific rationale.
- **Code and documentation in English. Talk to the user in Chinese.**
- **Stable string IDs** for graph edges; no entity framework. Claim, requirement, hypothesis and
  rule ids must be disjoint within a protocol, and the collision is refused at load.
- **Unknown is `None` internally and renders as unknown**, never as zero or false.
- **New scientific capability requires a protocol and tests**; it never enters the audit engine as a
  special case.
- **Third-party data is never committed.** Only the pin and the fetch script.

---

## 10. How to verify the state yourself

```console
# environment (see CONTRIBUTING.md for the full setup)
python --version                       # must be >= 3.12; a bare Windows `python` may be a stub
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"

# the three gates
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy src/qcjudge
```

If `tmp_path` tests error at setup, add `QCJUDGE_TEST_SCRATCH=./.test-scratch` (§6.2).

Fetch and verify the real corpus (it is present for the measurements above):

```console
.venv/Scripts/python tools/fetch_benchmark_data.py
.venv/Scripts/python tools/fetch_benchmark_data.py --verify
```

Run one audit end to end and read the report:

```console
python -m qcjudge.cli.main audit \
  --question transition_state \
  --input examples/01-transition-state-mode-identity/job.out \
  --ask "Is this structure the transition state for the C-C rotation step?" \
  --context molecule=dvb
```

That example reports `execution = PASS` with `structure = PASS` and overall
`PARTIALLY_SUPPORTED` — one imaginary frequency establishes Hessian order and nothing about the
pathway. It is the invariant in one page.

**Exit codes describe the run, not the verdict.** `0` whenever an audit was produced and printed,
including one whose evidence is insufficient. `2` means no audit could be produced. Read the finding
from `evidence.overall_status` in `--format json`.

---

## 11. Reading order for a new agent

1. `README.md` — positioning in one page.
2. `docs/scientific-scope.md` — what is asserted and what is refused (17 lines).
3. `docs/v0.1-plan.md` §1 for the verified state table, §3 the nine stages, §4 the module map and
   dependency rules, §5 the domain model and status definitions, §8 the debt register.
4. `docs/architecture.md` — the durable decisions and the failure-mode controls.
5. `src/qcjudge/domain/evidence.py` and `domain/assessment.py` — the vocabulary everything else uses.
6. `src/qcjudge/evidence/matching.py` — where "is this requirement met" is actually decided.
7. `tests/test_end_to_end.py` and `tests/test_acceptance_corpus.py` — the behaviour that must hold.
8. `docs/adapter-format.md` if touching imported analyses.

Then run the three gates before changing anything, so you know the baseline is green. For release
validation, build and install the wheel in an independent environment and run
`python -I tools/verify_installed_package.py`; the CI workflow contains the exact sequence.
