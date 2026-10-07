# Worked examples

Three synthetic ORCA-format outputs, each chosen to make one point about what an audit can and cannot
conclude. Every file is synthetic but uses ORCA's own printed wording and layout, so the
parser reads it exactly as it reads the real corpus.

Nothing here is fetched or vendored: the files are part of the repository and are small enough
to read.

| # | Example | Execution | Structure | Overall |
| --- | --- | --- | --- | --- |
| 1 | [One imaginary frequency](#1-one-imaginary-frequency-is-not-a-pathway) | PASS | PASS | `PARTIALLY_SUPPORTED` |
| 2 | [A converged minimum](#2-a-converged-minimum-is-not-a-saddle-point) | PASS | FAIL | `CONTRADICTED` |
| 3 | [A small singlet-triplet gap](#3-a-small-gap-is-not-a-risc-channel) | PASS | UNKNOWN | `PARTIALLY_SUPPORTED` |

Read together they are the project's claim in one page: **a calculation can succeed, and the
evidence can still be insufficient or even contradicted.** No example reports `SUPPORTED`, and
that is the honest result, not a shortcoming of the examples — the evidence types that would
support these claims (hole-electron analysis, spin-orbit couplings, IRC) come from analyses
QCJudge does not compute. The implemented JSON adapter can import those facts with source
association; user assertions stay capped at WEAK/INDIRECT.

## Running one

```console
python -m qcjudge.cli.main audit \
  --question transition_state \
  --input examples/01-transition-state-mode-identity/job.out \
  --ask "Is this structure the transition state for the C-C rotation step?" \
  --context molecule=dvb
```

Every example exits `0`: the audit ran and produced a report, so the run succeeded whatever it
found. Read the verdict from the report, or from `evidence.overall_status` with `--format json`.

## 1. One imaginary frequency is not a pathway

`01-transition-state-mode-identity/job.out` — a converged optimization whose Hessian has
exactly one imaginary mode, and nothing else.

**`PARTIALLY_SUPPORTED`.** The saddle-point claim is supported: one imaginary frequency
establishes the local Hessian order at the computed stationary point, and that is all it
establishes. The pathway claim is not addressed at all, because neither the imaginary mode was
inspected nor the path followed.

This is the case most likely to be over-read. The report says so in the protocol's own words:
*one imaginary frequency identifies local Hessian order, not pathway identity.* To close the
gap, supply `--condition mode_correspondence=...` if you have judged the mode, or IRC evidence
once an adapter can carry it.

## 2. A converged minimum is not a saddle point

`02-converged-minimum-is-not-a-saddle/job.out` — the same shape of job with no imaginary mode
at all.

**`CONTRADICTED`**, and note the two axes disagreeing on purpose: `execution` is **PASS**
because the calculation finished and converged, while `structure` is **FAIL** because what was
computed is a minimum. A converged minimum is a *successful* calculation, so it must not be
reported as a failed one; it is the saddle-point claim that is refuted, not the job.

The second claim becomes `NOT_ASSESSABLE` rather than `CONTRADICTED`: its premise is gone, so
there is nothing left to judge.

## 3. A small gap is not a RISC channel

`03-tadf-gap-is-not-a-risc-channel/job.out` — singlet and triplet manifolds at one consistent
level of theory, so a gap can be formed, and nothing about spin-orbit coupling.

**`PARTIALLY_SUPPORTED`**, capped by design. The gap claim is supported; the RISC claim is
`INSUFFICIENT` because a small gap is a *prerequisite* for efficient reverse intersystem
crossing, not evidence of it. However small the computed gap, the protocol will not exceed
`PARTIALLY_SUPPORTED` without coupling or kinetic evidence.

The report also refuses the stronger question. It never says the molecule is a TADF emitter,
and no fixed numerical cut-off is applied: reported gaps scatter by 0.1–0.15 eV in the
literature and depend on the functional by up to roughly 0.6 eV, so a threshold would be
invented precision.

## Where expert review comes in

Examples 1 and 2 declare an expert boundary on mode correspondence, because whether a mode
follows the proposed reaction coordinate cannot be encoded as a reproducible structured
assertion. If you have inspected the mode and judged it ambiguous, say so:

```console
python -m qcjudge.cli.main audit \
  --question transition_state \
  --input examples/01-transition-state-mode-identity/job.out \
  --context molecule=dvb \
  --condition mode_correspondence="the imaginary mode mixes rotation with bending"
```

The requirement then reports `REQUIRES_EXPERT_REVIEW` and the overall status follows. That is a
success condition of the design, not an error: the audit has recognised a question a human must
answer rather than guessing at it.
