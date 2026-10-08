# 4. Import an analysis for the selected excitation

**Expected verdict with the supplied analysis: `SUPPORTED`.** Execution is `PASS`.

Both files are synthetic demonstrations. `job.out` is hand-written ORCA-format text,
and `analysis.json` contains invented hole-electron descriptors attributed to
`synthetic-demo`. Neither file reports a real calculation, a Multiwfn run, or a
measurement. The name `demo-ct` is a label for this example.

Run this command from the project root after installing QCJudge:

```console
python -m qcjudge.cli.main audit --question ct_excitation --input examples/04-charge-transfer-analysis/job.out --context molecule=demo-ct --context state=S1 --analysis examples/04-charge-transfer-analysis/analysis.json --format json
```

The report has these selected fields:

```json
{
  "audit_scope": {
    "selected_calculation_ids": ["calc-1", "demo-ct-s1-hole-electron"],
    "association_issue": null
  },
  "execution": {"status": "pass"},
  "evidence": {"overall_status": "supported"}
}
```

The calculation supplies SCF convergence and the singlet energies used to identify
the S1 excitation. The imported D and Sr descriptors supply the spatial-analysis
evidence required by the current charge-transfer protocol. The recommended method
comparison remains missing, so `SUPPORTED` does not mean every possible check passed.

The analysis has its own `calculation_id`, `demo-ct-s1-hole-electron`.
Its `source_calculation_id`, `calc-1`, explicitly associates it with the single
input calculation; its `molecule` and `state` match the question. The report retains
the two sources and their provenance separately. In this command, `calc-1` is the
identifier assigned to the first and only parsed output.

Omit `--analysis` to see the same successful calculation produce
`INSUFFICIENT`: energies alone do not provide the required spatial evidence.

This example verifies the import workflow, explicit association, provenance, and
evidence coverage under the current protocol. It does not validate CT thresholds,
the chemical truth of the invented system, or a real molecule's charge-transfer
character. QCJudge applies no universal D/Sr cutoff here.
