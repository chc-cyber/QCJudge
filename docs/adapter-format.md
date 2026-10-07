# Importing an external analysis

QCJudge deliberately does not compute wavefunction analyses. Hole-electron descriptors,
natural-transition-orbital composition, spin-orbit couplings and intrinsic reaction coordinates
come from tools built for that purpose, and reimplementing them here would be a second, worse
implementation of someone else's algorithm inside a project about evidence.

So they are imported. The format below is the whole contract: one JSON document, one reader, no
heuristics. Everything is stated explicitly because the values are numbers an audit will reason
with, and a value read from the wrong field enters the record indistinguishable from a computed
one.

## The document

```json
{
  "format": "qcjudge.analysis_import/1",
  "analysis": "hole_electron",
  "producer": "Multiwfn",
  "producer_version": "3.8",
  "source_file": "dvb_s1_hole_electron.txt",
  "calculations": [
    {
      "calculation_id": "dvb-s1-analysis",
      "source_calculation_id": "calc-1",
      "molecule": "dvb",
      "state": "S1",
      "values": {
        "scf.converged": {"value": true, "unit": "none"},
        "tddft.state_count": {"value": 5, "unit": "states"},
        "hole_electron.d_index_angstrom": {"value": 2.41, "unit": "angstrom"},
        "hole_electron.sr_index": {"value": 0.31, "unit": "dimensionless"}
      }
    }
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `format` | yes | Must be exactly `qcjudge.analysis_import/1`. The version is checked rather than assumed, so a future format cannot be read as if it were this one. |
| `analysis` | no | Free text naming the analysis, for a human reading the export. |
| `producer` | yes | The tool that computed the values. It becomes the fact's producer, so the report can say where a number came from. |
| `producer_version` | yes | The producer's version. Without it an imported value cannot be reproduced or attributed precisely. |
| `source_file` | no | The file the analysis was exported from. Recorded in provenance; when absent, the path of the import itself is used. |
| `calculations` | yes | A non-empty list. Each entry becomes its own calculation, so one entry's descriptors cannot answer a claim about another. |
| `calculations[].calculation_id` | no | Unique ID for this result. Defaults to `analysis-N`; use explicit distinct IDs when importing several files. Reusing an ID across results is refused. |
| `calculations[].source_calculation_id` | for a related result | ID of the supplied main calculation this analysis describes. It preserves separate facts/producers while associating their evidence. |
| `calculations[].molecule` | no | Non-empty label checked against the question's `molecule` binding. |
| `calculations[].state` | no | Non-empty state label checked against the question's `state` binding. |
| `calculations[].values` | yes | A non-empty mapping of quantity to `{value, unit}`. |

## Quantities

A quantity must be a registered fact key **and** one this seam can carry. Both are checked: a
key existing is not the same as an import being able to assert it.

| Quantity | Unit | Meaning |
| --- | --- | --- |
| `scf.converged` | `none` | Whether the wavefunction behind the analysis converged. A boolean. |
| `tddft.state_count` | `states` | How many excited states were characterized. |
| `hole_electron.d_index_angstrom` | `angstrom` | Average hole-electron distance. |
| `hole_electron.sr_index` | `dimensionless` | Hole-electron overlap. |
| `nto.dominant_pair_contribution` | `dimensionless` | Share of the transition described by its dominant NTO pair. |
| `spin_orbit.coupling_cm1` | `cm**-1` | Singlet-triplet spin-orbit coupling. |
| `irc.connects_two_minima` | `none` | Whether an IRC run reached two distinct minima from the saddle point. A boolean. |

Anything else is refused with the offending name, because a typo that were merely ignored would
become silently missing evidence — the failure mode this project least wants.

`scf.converged` is in the list because an analysis of a calculation asserts something about that
calculation. Without it every gated requirement comes out `NOT_ASSESSABLE`: correctly, since a
descriptor says nothing about whether the wavefunction behind it converged, but uselessly, because
a tool that computed the descriptor knows.

`irc.connects_two_minima` deliberately records the weakest thing an IRC run establishes. Reaching
two minima is not the same as reaching the *intended* ones; identifying those is the question the
researcher asked, and the protocol declines to answer it for them. It is declared `MODERATE` for
that reason.

## Units

A unit is required for every value. Silence is not permission to assume one.

Exact equivalences are converted, because the arithmetic carries no judgement:

| Recorded in | Also accepted |
| --- | --- |
| `angstrom` | `a`, `bohr` |
| `cm**-1` | `cm-1`, `wavenumber` |
| `dimensionless` | `none`, `states`, `count`, `bool`, `""` |

Anything else is refused rather than converted. A value stated in the wrong unit is worse than a
missing one: it looks like an answer. Convert before exporting.

A boolean value keeps its type, because a convergence flag is read as a flag. Units are
validated for booleans too. Only `scf.converged` and `irc.connects_two_minima` accept booleans;
numeric 0/1 cannot substitute for a flag. `tddft.state_count` accepts non-negative JSON integers,
not booleans or fractional/float counts. Zero states remain a fact but do not identify an excitation.
Other values must be finite numbers; D is non-negative, Sr and NTO contribution are in [0,1],
and signed SOC values are retained. These are quantity domains, not universal CT/TADF thresholds.

## Associating an analysis with its target

For `--input job.out`, the parsed result defaults to `calc-1`. For a directory, sorted filenames
receive `calc-1`, `calc-2`, etc. An imported SOC or IRC result must state
`source_calculation_id: "calc-1"` to contribute alongside that output. Its own `calculation_id`
stays distinct. Links to absent results, cycles, conflicting metadata, and explicit molecule/state
mismatches yield `NOT_ASSESSABLE`. Several unlinked roots are also unassessable unless `--target`
(or context `calculation_id`) selects one; unrelated roots remain visible but do not contribute.
A single self-contained result can be audited without a source link. Association is declared by
the supplier and recorded; QCJudge does not infer molecular identity from a filename.

An IRC flag of `false` is preserved as a fact, but cannot derive evidence asserting that two
minima were reached. It does not by itself refute the existence of a transition state.

## What the audit does with it

The imported values become facts with the producer recorded as `qcjudge.adapter.<producer>`.
Evidence derived from those facts carries `origin: adapter`, so the report distinguishes a number
the calculation emitted from one an external tool supplied.

The importer never chooses evidence strength. A protocol declares what a descriptor is worth,
exactly as it does for a parsed value — see `EvidenceDerivation` in `src/qcjudge/protocols/v1.py`.

## Using it

```console
qcjudge audit --question tadf_potential --input job.out --analysis soc.json --context molecule=dvb
```

## Where the format comes from

No tool writes this format natively. Converting an export into it is a small, explicit step, which
is deliberate: the conversion is where a human decides what a number means and in what unit, and
that decision should be visible rather than buried in a parser heuristic.

Licence note: Multiwfn is not an OSI-approved open-source project. QCJudge consumes its exported
text and never bundles or links it. See `docs/v0.1-plan.md` section 10.
