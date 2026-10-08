# Benchmarks and evaluation data sources

Where QCJudge's test and benchmark data can come from, what each source can and cannot
establish, and what the licence of each one permits.

Status: research notes, current as of September 2026. Verify every licence before vendoring
any file.

## 1. The four layers a benchmark must cover

QCJudge is not a predictor, so "a benchmark" means four different things at four different
layers. Three layers have ready sources. The fourth does not, and cannot, because nobody
has ever published it.

| Layer | What it establishes | Public source |
| --- | --- | --- |
| L1 parsing | that extraction does not invent or lose values | cclib-data, NOMAD |
| L2 facts | that extracted numbers match authoritative values | CCCBDB, QUEST |
| L3 methodology | that we warn and defer rather than conclude | QUEST/LJCT, Transition1x, TADF literature sets |
| L4 evidence adequacy | that we judge sufficiency correctly | **none — must be constructed** |

The L4 gap is the point of the project, so the benchmark for it has to be built. Section 4
proposes how to build it without paying for expert labelling.

## 2. L1 — parsing corpora

**cclib-data** (`cclib/cclib-data`, GitHub). A data-only repository of real log files used
as cclib regressions. Organised by program and version (`ORCA/`, `Gaussian/Gaussian09/`,
`QChem/`, ...) with a `regressionfiles.yaml` registry mapping each file to its assertions.

Why it matters more than it looks: it deliberately contains the failures. Known entries
include an unconverged geometry optimisation (`dvb_gopt_unconverged.log`), an SCF that
stopped early, an ORCA 4.0 file with an unparsable float literal, a constrained optimisation
with an extra line before the gradients, and Truncated geometry sections. Those map almost
directly onto our `UnavailableReason` values, and they are the corpus our parser contract
tests need.

Licence: cclib itself is BSD-3-Clause; confirm the repository's own terms before
redistributing any file.

**In use.** `tools/fetch_benchmark_data.py` fetches a twelve-file ORCA subset pinned to commit
`a16cc80ea29e8baec60abd0df346ce6862f52531` into an ignored directory, verifying every file
against `tools/benchmark_manifest.json`. It spans ORCA 2.6 to 5.0 and includes the awkward
cases: an unconverged optimisation, a job that hit its cycle limit, a very long input echo,
and a spin-orbit calculation. `tests/test_real_orca_output.py` runs the parser over that corpus
and is skipped until it has been fetched. Reading the markers off these files instead of
assuming them corrected five parser defects; see the changelog.

**NOMAD** (NOMAD Repository and Archive). The largest collection of raw computational
output files, kept in the format the code produced. Supports roughly 40 codes including
ORCA, Gaussian, CP2K, NWChem. Download requires no registration; data are published under
CC-BY-4.0 (older uploads under CC-BY-3.0); a REST API and Python client exist.

Its value here is the opposite of cclib-data's: it is unfiltered and dirty, which is what
you want for robustness and fuzz testing. Its limitation is that it is materials-science
oriented, so molecular and molecular-excited-state entries are a minority; filter on code
and system type.

## 3. L2 — reference values

**CCCBDB** (NIST Standard Reference Database 101, DOI 10.18434/T47C7Z, Release 22). About
680 small gas-phase molecules with experimental and computed thermochemistry, geometries,
vibrational frequencies, rotational constants, dipole moments and polarisabilities, mostly
with published uncertainties. Two sections are directly on point for us: singlet-triplet
gaps under Excited State, and transition-state frequencies, geometries and IRC under
Transition State. Citation is required for published work.

One trap to encode as a dedicated validator: CCCBDB's atomisation energy is **D0, zero-point
included**, while an SCF calculation yields **De without zero-point**. They differ by
roughly 3-10 kcal/mol for small molecules. This is a textbook instance of the exact class of
error QCJudge exists to catch — a computed fact silently compared against a non-equivalent
reference — and it deserves a named rule rather than a comment.

**QUEST** (`pfloos/QUESTDB`, GitHub; Loos et al., J. Chem. Theory Comput. 2025, 21, 8010).
1489 aug-cc-pVTZ vertical transition energies for valence and Rydberg states, plus states
with partial or genuine double-excitation character. Most values are within +/-0.05 eV of
the FCI estimate. Ships raw data and analysis tools.

Licence warning: the figshare deposit is **CC BY-NC 4.0 — non-commercial**. It cannot be
bundled into a BSD-3-Clause distribution. Treat it as an optional, user-fetched external
data source and document that clearly.

## 4. L3 — methodological cases

These are the sources that let us test the "warn and defer" behaviour, and they also supply
the quantitative justification for the protocol's expert-review boundaries.

### Charge transfer

- **LJCT set** (Loos and Jacquemin): 30 intramolecular CT transitions across 17
  conjugated compounds, with CC-based theoretical best estimates, and — importantly —
  the original work splits the transitions into *mild* and *strong* CT based on
  electron-hole separation from the ADC(2) wavefunction. That split is the closest thing
  to an existing label for CT character.
- **Szalay intermolecular CT set**: 14 excitation energies over 9 bimolecular complexes
  chosen to give near-complete charge separation. References at CCSDT-3/cc-pVDZ.
- **Baer Ar-TCNE complexes**: benzene, toluene, o-xylene and naphthalene with TCNE,
  compared against experimental gas-phase values.
- **Bogo and Stein, Zenodo record 12802817**: intermolecular CT excitation energies *and*
  density-based CT descriptors (D_CT) across multiple functionals and basis sets, with
  EOM-CC reference data and CSV files. This is the one open dataset found that ships
  quantitative CT descriptor values, which is exactly the shape of the "hole-electron
  analysis" evidence type the CT protocol demands.

Two published findings should be quoted in the protocol itself, because they justify design
decisions rather than merely informing them:

1. The literature states plainly that identifying CT excitations "often relies on subjective
   findings", and that the D_CT threshold separating local from charge-transfer excitations
   sits near 0.3-0.4 A and shifts with the method and with whether relaxed or unrelaxed
   densities are used. That is the direct justification for asserting no universal
   threshold and routing donor/acceptor partitioning to expert review.
2. Conventional TD-DFT underestimates intermolecular CT energies by a mean signed error
   around -2.13 eV. That gives the long-range-sensitivity WARNING a citable magnitude.

### TADF

- **Huang and Cole, Scientific Data 2024, 11:80**: a TADF database text-mined from 2733
  papers — 25 482 records, 5349 with SMILES, covering maximum emission wavelength, PLQY,
  ΔEST and delayed lifetime, at 82% overall precision and 91% SMILES accuracy. Useful as
  *literature-reported* values for constructing realistic cases. It is not a gold standard:
  82% precision means roughly one in five records is wrong, which is itself a useful test
  of how we handle conflicting evidence.
- **The 747-molecule and 231-molecule xTB-based TADF benchmarks** (Tchapet Njafa et al.).
  Two numbers from this work belong in our methodology checks: inter-report experimental
  scatter in ΔEST is 0.1-0.15 eV, and functional dependence reaches 0.58 eV. Any ΔEST
  consistency check must be calibrated against those magnitudes, not against chemical
  intuition.
- A cautionary real case worth citing in the README: an earlier version of that work
  reported a mean absolute error of 0.025 eV and was subsequently withdrawn after review
  found feature-target leakage — ΔEST was being regressed on its own constituents,
  E(S1) - E(T1). This is a live specimen of the failure mode QCJudge is built to catch.

### Transition state

**Transition1x** (Schreiner et al., Scientific Data 2022, 9:779; figshare 19614657;
`gitlab.com/matschreiner/T1x`). 9.6 million configurations along NEB paths for 10 000
organic reactions at ωB97x/6-31G(d), generated with ORCA, with reactant, transition-state
and product configurations retained per reaction, and non-converged paths explicitly
discarded. It supports three constructions: full path supplied (satisfies the pathway group),
transition-state geometry alone (partial), and cross-checking our zero/one/multiple
imaginary-frequency classification against known saddle points.

Caveat: it stores energies, forces and geometries in HDF5, not ORCA output text. It is a
source of reference values and geometries, not of parser fixtures.

### General methodological mismatches

Multi-method benchmark collections such as GMTKN55 are useful for constructing the specific
failure case where a researcher compares values computed with different functionals or basis
sets. That case must produce a methodology WARNING, never a verdict.

## 5. L4 — evidence adequacy, which must be constructed

No public benchmark labels whether an evidence package is sufficient for a scientific
question, because that requires a question, an evidence inventory, and a sufficiency
judgement, and the third has never been annotated at scale.

**Route A — ablation labelling. Recommended first, because it needs no human labels.**

Take a system with high-level reference data (a QUEST or LJCT entry, a Transition1x
reaction, a CCCBDB singlet-triplet pair), then systematically remove evidence and let the
label follow from the removal:

| Construction | Expected requirement outcome |
| --- | --- |
| full set: energies, oscillator strengths, hole-electron descriptors | SUPPORTED |
| descriptors removed, energies retained | INSUFFICIENT |
| state assignment removed | INSUFFICIENT |
| file truncated mid-output | NOT_ASSESSABLE |
| values replaced with an ambiguous duplicate match | NOT_ASSESSABLE + expert boundary |
| TS with the full IRC path | SUPPORTED (via the ANY_ONE group) |
| TS with only the frequency list | PARTIALLY_SUPPORTED |
| a minimum submitted as a transition state | CONTRADICTED |

The expected label is decided by what we deleted, so no annotation budget is required. The
limit is real and must be stated: this validates the engine's reasoning consistency, not our
understanding of real research practice.

**Route B — real cases, small and expert-labelled.**

Take published claims together with the evidence the authors actually provided, and have
domain experts label sufficiency independently. The sample will be small (tens), and it is
the only route that answers "what does inadequate evidence actually look like in practice".

AutoMat (Huang et al., arXiv 2605.00803) is the packaging template to imitate: 85
subject-matter-expert-curated claims, each with a claim statement, an `agent_view/` of what
the agent may see, and a `reference/` ground truth. Two differences matter. AutoMat's task is
*reproduction* — reconstruct and execute the workflow — whereas QCJudge assesses the adequacy
of evidence that already exists and executes nothing. And AutoMat is a gated Hugging Face
dataset under CC-BY-4.0, so it cannot be redistributed; only open-access paper PDFs are
bundled, paywalled ones are placeholders.

Related benchmarks worth citing in the positioning section, since our claim is that we are
narrower than all of them: CORE-Bench (task-level, from provided code and data), REPRO-Bench
(paper-level, social science), SciReplicate-Bench, PaperBench, ScienceAgentBench, and
Matter-of-Fact.

## 6. Evaluation metrics

Accuracy is the wrong headline metric for an auditor. Report these instead:

1. **False-SUPPORTED rate.** The only unacceptable error is declaring insufficient evidence
   sufficient. It gets its own metric and its own escalation policy.
2. **Per-requirement status agreement** with the constructed label, not agreement on a
   single overall verdict.
3. **UNKNOWN discipline.** Count of cases where absent data was rendered as false or zero.
   The target is exactly zero, asserted as an invariant rather than a score.
4. **Trace completeness.** Fraction of SUPPORTED assessments whose every cited fact resolves
   to a file and a location.
5. **Reproducibility.** Identical inputs and protocol version must produce the same report
   content after excluding creation/extraction timestamps. The replay tool separately checks
   versions and parser diagnostics; see [the replay procedure](replay.md).

## 7. Licence matrix

| Source | Licence | May we redistribute it? |
| --- | --- | --- |
| cclib-data | to verify (cclib itself is BSD-3-Clause) | verify LICENSE first; prefer fetch-only |
| NOMAD | CC-BY-4.0 (early uploads CC-BY-3.0) | yes, with attribution; fetch on demand |
| CCCBDB | NIST SRD 101, citation required | cite, do not mirror wholesale |
| QUEST | **CC BY-NC 4.0 — non-commercial** | **no** — optional fetch only |
| Transition1x | article CC-BY; figshare record to verify | fetch on demand |
| Huang and Cole TADF database | Scientific Data, CC-BY | yes, with attribution |
| AutoMat | CC-BY-4.0 but **gated** | no redistribution; apply for access |

Consequence, and this is a design decision rather than a caveat: **no benchmark data is
vendored into this repository.** The repository carries a small number of clearly labelled
synthetic fixtures sufficient for the unit tests, and a fetch script with checksums for
anything real. That keeps the repository small, keeps non-commercial and gated data out of
the distribution, and keeps the BSD-3-Clause licence of QCJudge honest.

## 8. Adoption order

Measured local adoption as of 2026-10-08:

- **Implemented:** synthetic acceptance cases, parser-to-audit regressions, 12 pinned real ORCA
  output files fetched by `tools/fetch_benchmark_data.py`, generated behavior checks, and local
  raw-input/checksum replay bundles. The complete CT example is explicitly synthetic.
- **Pending:** independent expert labels for evidence adequacy and scientific validation of
  state identity, donor/acceptor interpretation and coupling significance. The current tests do
  not measure a real-world false-SUPPORTED rate.
- **Candidates:** the external datasets discussed above are research directions, not integrated
  benchmark claims. Verify their current access, licence and fit before adoption. No CCCBDB
  reference evaluator or LJCT/Stein ablation generator is implemented in V0.1.

Prioritize a small set of reviewable expert-labelled cases, preserving original inputs,
assumptions, versions and expected requirement-level outcomes. Then extend the ablation
generator around those cases. Replaying a few examples across development versions does not
complete the full compatibility gate.

One further recommendation: publish the benchmark *generator*, not just the results. Since
the L4 layer has no prior art, a results-only release would leave our labels unverifiable.
Shipping the ablation generator alongside it turns the gap into a contribution.
