# QCJudge — agent handoff

Written at the end of a review-and-repair series that took the project from "declarative but not
operative" to M4 complete. Everything below was measured in that session, not transcribed from the
plan. Where the plan and this file disagree, this file is the newer measurement and the plan entry
should be corrected.

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
reader. Which one fires is decided by the parser's `UnavailableReason` per fact, never by the audit
engine.

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

### 4.2 Module map (38 source files, ~3,900 lines)

```
cli/main.py             argparse only; exit-code policy; no science        (275)
render/text.py          human-readable report                              ( 67)
render/json_report.py   the stable machine-readable contract               (160)

audit/engine.py         orchestration only; no rule or requirement ids     (131)
audit/aggregation.py    requirement -> claim -> hypothesis -> overall      (151)
audit/trace.py          the inspectable why-chain                          ( 51)

evidence/matching.py    requirement -> evidence, groups, dependencies      (373)
evidence/derivation.py  facts -> evidence at protocol-declared strengths   ( 90)
evidence/facts/projection.py  Observation -> ExtractedFact + arithmetic    (349)

adapters/json_analysis.py   the documented external-analysis import        (254)

parsers/base.py         the reader contract                                ( 21)
parsers/orca.py         the declared ORCA subset                           (750)

validators/registry.py  implementation_key -> rule callable                ( 26)
validators/collect.py   fact reading + absence explanation                 ( 55)
validators/execution.py convergence and Hessian order                      (111)
validators/methodology.py consistency checks                               ( 59)

protocols/v1.py         the three built-in protocols                       (538)

domain/                 pure types; imports nothing but stdlib + errors  (~1,150)
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
| Tests | `pytest` | **380 collected: 378 passed, 2 skipped, 0 failed** |
| Types | `mypy --strict src/qcjudge` | clean, **38 files** |
| Lint | `ruff check .` | clean |
| Format | `ruff format --check` | **not a gate** — see D-33 |
| Repository | `git status` | **no `.git`; git is not installed on this machine** |

The 2 skips are `tests/test_real_orca_output.py` entries that need a corpus file not present; the
other 73 items in that file run against the fetched corpus.

### 5.2 Milestones

| Milestone | State |
| --- | --- |
| M0 Foundation | complete |
| M1 Evidence kernel | complete |
| M2 Parser boundary | complete |
| M2.5 End-to-end status correctness | complete |
| M3 CLI and reports | complete |
| M4 Adapter seam | complete |
| M5 Hardening and release | **partly done** — CI defined and tested but never run; no property tests; no tag |
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

### 5.6 Test suite (31 files)

By purpose, in the order they are worth reading:

| File | Items | Why it exists |
| --- | --- | --- |
| `test_acceptance_corpus.py` | 20 | The scenario matrix. Proves technical success ≠ scientific sufficiency. |
| `test_audit_separation.py` | 12 | The independence property as examples. |
| `test_layering.py` | 79 | The import-boundary matrix over every source file. |
| `test_real_orca_output.py` | 75 | The parser against real ORCA 2.6–5.0 output. |
| `test_orca_parser.py` | 25 | The parser contract on synthetic fixtures. |
| `test_end_to_end.py` | 23 | **Crosses the parser→audit boundary.** See §7. |
| `test_adapter.py` | 25 | The import seam, mostly refusals. |
| `test_protocols.py` | 23 | Protocol graph integrity. |
| `test_cli.py` | 16 | Exit-code policy and both researcher channels. |
| `test_golden_report.py` | 14 | JSON shape + byte-for-byte text snapshots. |
| `test_ci_configuration.py` | 14 | Holds the workflow to its own claims. |
| `test_inventory.py` | 14 | Domain invariants. |
| `test_derivation.py` | 13 | Declared strengths, origin inheritance. |
| `test_examples.py` | 11 | The examples keep producing their documented verdicts. |
| `test_insufficiency_conditions.py` | 9 | D-32's behaviour. |
| `test_fetch_benchmark_data.py` | 7 | The manifest refusal rules. |

Support modules: `tests/support.py` (hand-built inventories), `tests/golden.py` (the one
deterministic report), `tests/conftest.py` (scratch routing, §6.2).

---

## 6. Current difficulties

### 6.1 BLOCKED — no git repository, and CI has never run (D-13)

**Concrete condition.** `git --version` fails; `Get-Command git` finds nothing; searching both
`C:\` and `E:\` for `git.exe` returns nothing. Git is not installed on this machine.

**What that prevents.** `git init`, the first commit, and therefore the first real execution of
`.github/workflows/ci.yml`. The project has no history at all.

**What is already in place, ready to commit:**

- `.gitignore` — venv, caches, `.benchmark-data/`, `.test-scratch/`
- `.gitattributes` — LF normalisation, with `tests/data/**` marked `-text` because those fixtures
  are compared byte for byte. Without this a Windows checkout with `core.autocrlf=true` fails the
  golden text tests on a clean clone, and the failure looks like a rendering regression.
- `.github/workflows/ci.yml` — ruff + mypy + pytest on Python 3.12 and 3.13 across Linux, macOS and
  Windows, with the real ORCA corpus fetched as a `continue-on-error` step that cannot fail the
  build.
- `tests/test_ci_configuration.py` — 14 tests holding the workflow to its own claims.

**Do not mistake the last item for a green build.** The workflow configuration is *tested*; it has
never *executed*. That distinction is recorded in the plan's M3 gate note and in D-13.

**What is needed.** On a machine with git:

```console
git init
git add .
git commit -m "QCJudge v0.1 foundation through M4"
git remote add origin <url>
git push -u origin main
```

Then confirm the workflow runs green. That first run also executes the 75 real-corpus items
automatically for the first time — roughly a fifth of the suite that currently only runs where
someone has fetched the corpus.

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

### 8.1 Needs a decision or an external machine

1. **D-13 — create the repository.** Three commands on a git-capable machine, then confirm the
   workflow runs green. Blocks nothing else in the code but blocks reproducible history, the CI
   matrix, and automatic execution of the real-corpus tests.
2. **D-33 — decide formatting.** Either adopt `ruff format` (format the whole tree in the same
   change, then add the gate) or leave it explicitly out. Currently "out", recorded as a decision.
3. **D-32 residual — machine-readable "provided but not inspected".** `ts.mode_identity` declares no
   `required_facts`, so the engine cannot tell that the frequency calculation *was* supplied and only
   the inspection is missing. The protocol's prose covers it; the machine-readable distinction does
   not exist. Designing it means deciding how a requirement states "this was provided but is
   unusable", which the domain model cannot currently express.

### 8.2 Optional scope, each a further fact key rather than a seam change

4. `risc_rate` (`s**-1`) and `vibronic_coupling_analysis` producers for TADF.
5. `reaction_path_following` as distinct from IRC, and `attachment_detachment_density` for CT.
6. `method_comparison` / `range_separation_validation` — these assert something *about* the
   calculation rather than describing an analysis, so they need thought about whether they belong in
   the adapter seam at all.

### 8.3 M5 remainder

7. Property tests (`hypothesis`) for the projection and matcher.
8. Redacted real-world outputs beyond the current corpus.
9. Dependency and attribution documentation for the adapter seam.
10. `v0.1.0` tag — not before D-13.

### 8.4 Deliberately not started

11. **M6 LLM layer**, shipped as an optional extra the core never imports. Gate: removing the extra
    leaves the entire suite green.

### 8.5 Open debt carried deliberately (D-19 … D-22)

| ID | Sev | Note |
| --- | --- | --- |
| D-19 | L | Claims bind through string templates, so an under-specified question fails at audit time rather than question construction. Fails loudly and names the missing keys; acceptable for V0.1. |
| D-20 | M | A multi-job file contributes only its first command line, so method and basis describe that job alone. Found on `ORCA4.2/long-input.out` (200 jobs). Frequency blocks were fixed for this reason (D-28); method/basis were not. |
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

Fetch the real corpus to widen coverage by ~75 items:

```console
.venv/Scripts/python tools/fetch_benchmark_data.py
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

Then run the three gates before changing anything, so you know the baseline is green.
