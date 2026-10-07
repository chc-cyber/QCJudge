# Scientific scope and epistemic policy

QCJudge V0.1 audits only charge-transfer excitation character, TADF potential, and
transition-state validation. It assesses whether declared computational evidence supports,
partially supports,
contradicts, or fails to address a claim under explicit assumptions.

The system distinguishes observations, computed facts, method assumptions, interpretations,
evidence, and claims. For example, a computed singlet-triplet gap is a fact; its relevance to RISC is
an interpretation; efficient TADF is a stronger claim. Likewise, exactly one imaginary frequency
supports first-order saddle-point character for a computed Hessian, but does not identify the
chemical pathway.

V0.1 will not determine scientific truth, prescribe universal CT or TADF thresholds, replace expert
inspection of ambiguous states or modes, run quantum-chemistry jobs, or reproduce workflow agents,
HPC systems, and wavefunction-analysis packages.

Required scenario coverage includes successful/sufficient and successful/insufficient cases, SCF
failure, unconverged optimization, zero/one/multiple imaginary frequencies, a one-mode TS without
path evidence, TADF evidence containing only a singlet-triplet gap, and TDDFT energies without CT
analysis.
