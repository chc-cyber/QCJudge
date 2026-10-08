# 1. One imaginary frequency is not a pathway

**Verdict: `PARTIALLY_SUPPORTED`** — execution `PASS`, structure `PASS`, evidence partial.

The job converged and its Hessian has exactly one imaginary mode. That supports the
saddle-point claim and nothing more.

```console
python -m qcjudge.cli.main audit \
  --question transition_state \
  --input examples/01-transition-state-mode-identity/job.out \
  --ask "Is this structure the transition state for the C-C rotation step?" \
  --context molecule=dvb
```

```text
QCJudge scientific audit

Question
Is this structure the transition state for the C-C rotation step?
context: molecule=dvb
protocol: transition_state 1.1.1
audit calculations: calc-1

Execution validity
PASS
- [PASS] SCF converged.
- [PASS] Geometry optimization converged.

Structural validation
PASS
- [PASS] This Hessian is first-order at the computed stationary point.

Methodological checks
UNKNOWN
- no methodology check was declared by this protocol

Evidence

Hypothesis [PARTIALLY_SUPPORTED] The optimized structure is the transition state for the proposed reaction step.
  Claim [SUPPORTED] The optimized structure of dvb is a first-order saddle point of the computed potential energy surface.
    [SUPPORTED] ts.stationary_point: Met by evidence of the accepted type: derived:ts.saddle_from_opt_and_freq:calc-1.
  Claim [INSUFFICIENT] The saddle point connects the intended reactant and product of the proposed step.
    [INSUFFICIENT] ts.mode_identity: No evidence of an accepted type was supplied. This requirement declares as insufficient: (1) The imaginary frequency is known but its mode was never inspected.
      missing: normal_mode_inspection
    [INSUFFICIENT] ts.pathway_connection: No evidence of an accepted type was supplied.
      missing: irc, reaction_path_following

Overall evidence assessment
PARTIALLY_SUPPORTED
```

## Why the second claim is not supported

One imaginary frequency establishes the local Hessian order *at the computed stationary point*.
It does not identify the chemical pathway: a first-order saddle point on the computed surface
may connect a different pair of basins from the ones the question intends. Establishing that
connection needs the mode inspected by a person or the path followed in both directions.

To record a mode judgement you have made:

```console
python -m qcjudge.cli.main audit \
  --question transition_state \
  --input examples/01-transition-state-mode-identity/job.out \
  --context molecule=dvb \
  --condition mode_correspondence="the imaginary mode mixes rotation with bending"
```

`ts.mode_identity` then reports `REQUIRES_EXPERT_REVIEW` and the overall status follows, because
the protocol declares that mode correspondence cannot be encoded as a reproducible structured
assertion. The report quotes both the protocol's reason and yours.

## Note on the wording

`ts.mode_identity` reports `INSUFFICIENT` and, alongside the engine's "No evidence of an accepted
type was supplied", restates the protocol's own account of the gap: *the imaginary frequency is
known but its mode was never inspected.* That second sentence is the more precise one, and it is
the reason `insufficiency_conditions` exists. All of a requirement's declared conditions are
listed rather than one being selected, because the conditions are prose and choosing between
them would be a guess.

One imprecision remains: the requirement declares no `required_facts`, so the engine cannot tell
that the frequency calculation *was* supplied and only the inspection is missing. The protocol's
sentence covers it; the machine-readable distinction does not exist yet.
