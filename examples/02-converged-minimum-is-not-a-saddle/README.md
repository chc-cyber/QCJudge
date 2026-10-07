# 2. A converged minimum is not a saddle point

**Verdict: `CONTRADICTED`** — execution `PASS`, structure `FAIL`, evidence contradicted.

The same shape of job as example 1, with no imaginary mode: the optimization converged on a
minimum, and a minimum is not a first-order saddle point.

```console
python -m qcjudge.cli.main audit \
  --question transition_state \
  --input examples/02-converged-minimum-is-not-a-saddle/job.out \
  --ask "Is this structure a saddle point for the proposed step?" \
  --context molecule=dvb
```

```text
QCJudge scientific audit

Question
Is this structure a saddle point for the proposed step?
context: molecule=dvb
protocol: transition_state 1.0.0

Execution validity
PASS
- [PASS] SCF converged.
- [PASS] Geometry optimization converged.

Structural validation
FAIL
- [FAIL] The computed Hessian has 0 imaginary frequencies, not one.

Methodological checks
UNKNOWN
- no methodology check was declared by this protocol

Evidence

Hypothesis [CONTRADICTED] The optimized structure is the transition state for the proposed reaction step.
  Claim [CONTRADICTED] The optimized structure of dvb is a first-order saddle point of the computed potential energy surface.
    [CONTRADICTED] ts.stationary_point: Available evidence rules this out: The computed Hessian has 0 imaginary frequencies, not one.
  Claim [NOT_ASSESSABLE] The saddle point connects the intended reactant and product of the proposed step.
    [NOT_ASSESSABLE] ts.mode_identity: The premise 'ts.stationary_point' is not established (contradicted), so this requirement cannot be judged.
      missing: normal_mode_inspection
    [NOT_ASSESSABLE] ts.pathway_connection: The premise 'ts.stationary_point' is not established (contradicted), so this requirement cannot be judged.
      missing: irc, reaction_path_following

Overall evidence assessment
CONTRADICTED
```

## The two axes disagree on purpose

`execution` is **PASS** and `structure` is **FAIL**, and that is the point of keeping them
apart. The calculation *succeeded*: SCF converged, the geometry converged, the Hessian is
complete and every mode is real. What failed is not the job but the claim — the computed object
is a minimum, so "this is a first-order saddle point" is refuted.

Reporting this as a failed calculation would be wrong in both directions: it would suggest
something went wrong with the run, and it would suggest that no conclusion is available, when
in fact a decisive one is.

## Why the second claim is NOT_ASSESSABLE

Its premise is contradicted, so there is nothing left to judge and the report says so rather
than stacking a second contradiction on a claim whose foundation is gone.
