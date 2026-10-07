# 3. A small gap is not a RISC channel

**Verdict: `PARTIALLY_SUPPORTED`** — capped by design, however small the computed gap.

The job reports singlet and triplet manifolds at one consistent level of theory, so a gap can
be formed, and reports nothing about spin-orbit coupling.

```console
python -m qcjudge.cli.main audit \
  --question tadf_potential \
  --input examples/03-tadf-gap-is-not-a-risc-channel/job.out \
  --ask "Is the singlet-triplet gap small enough for this molecule to show TADF?" \
  --context molecule=dvb
```

```text
QCJudge scientific audit

Question
Is the singlet-triplet gap small enough for this molecule to show TADF?
context: molecule=dvb
protocol: tadf 1.0.0

Execution validity
PASS
- [PASS] SCF converged.

Structural validation
UNKNOWN
- no structure check was declared by this protocol

Methodological checks
PASS
- [PASS] All recorded quantities share one method and basis set.

Evidence

Hypothesis [PARTIALLY_SUPPORTED] The available calculations provide evidence consistent with TADF potential.
  Claim [SUPPORTED] The relevant singlet and triplet states of dvb are separated by a small energy gap under the stated method.
    [SUPPORTED] tadf.singlet_triplet_states: Met by evidence of the accepted type: derived:tadf.gap_from_state_manifolds:calc-1.
  Claim [INSUFFICIENT] A spin-forbidden channel capable of repopulating the singlet state of dvb is supported by evidence.
    [INSUFFICIENT] tadf.risc_coupling: No evidence of an accepted type was supplied.
      missing: spin_orbit_coupling, risc_rate, vibronic_coupling_analysis
  Claim [INSUFFICIENT] The radiative singlet decay channel of dvb is characterized.
    [INSUFFICIENT] tadf.radiative_channel: No evidence of an accepted type was supplied.
      missing: oscillator_strength, radiative_rate

Overall evidence assessment
PARTIALLY_SUPPORTED
```

## Why this is the flagship case

A small singlet-triplet gap is a **prerequisite** for efficient reverse intersystem crossing,
not evidence of it. The spin-forbidden channel also needs spin-orbit coupling, a rate estimate,
or a vibronic analysis. The protocol therefore caps the overall status at
`PARTIALLY_SUPPORTED` whenever only energetics are available, no matter how small the computed
gap is — this is enforced by an acceptance test rather than by prose.

## What the report refuses to say

It never states that the molecule is a TADF emitter. The headline says the evidence is
"consistent with TADF potential", and the protocol records why the stronger statement is out of
reach:

- device-level TADF performance is not inferred;
- no fixed numerical gap cut-off is applied, because reported gaps scatter by 0.1–0.15 eV in
  the literature and depend on the functional by up to roughly 0.6 eV.

## Checked, not assumed

`Methodological checks` reports `PASS` because a methodology rule *was* declared and ran: the
compared state energies share one method and basis set. `Structural validation` reports
`UNKNOWN` with "no structure check was declared by this protocol", because this protocol
declares none — an axis nobody examined must not read as one that passed.
