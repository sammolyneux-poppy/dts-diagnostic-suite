# DTS Diagnostic Test Suite

Validation-of-validation layer for the DTS Proof Verification Battery. This suite confirms that each verification test **actually detects what it claims to detect** by running positive and negative controls with known outcomes.

## Methodology

Following standard experimental science practice:

- **Positive controls (D0):** Valid synthetic data that should pass every test. Confirms no false alarms.
- **Negative controls (D1–D9):** Synthetic data with exactly ONE injected defect each. Confirms the corresponding test detects it.

If a test fails to detect a known defect, or false-alarms on valid input, the test is buggy.

## Diagnostic Matrix

| ID | Defect | Target Test | Expected Detection |
|----|--------|-------------|-------------------|
| D0 | None (perfect) | All tests | All PASS |
| D1 | Dead axiom | V1 | SILENT classification |
| D2 | Non-injective encoding | V2 | Decode mismatch |
| D3 | No phase transition | V8-Sim1 | Concordance test 2,4 FAIL |
| D4 | Exponential (not power-law) | V8-Sim2 | Concordance test 1 FAIL |
| D5 | No tier separation | V8-Sim3 | Concordance tests 5,7,8 FAIL |
| D6 | Wrong power-law α | V10-Pred1 | α out of range |
| D7 | Drake violation | V10-Pred2 | CV > threshold |
| D8 | Landauer violation | V10-Pred3 | Margin < 1 |
| D9 | Nonlinear indels | V10-Pred4 | Linear not preferred |

## Quick Start

```bash
# Run all diagnostics
python3 run_diagnostics.py

# Run individual harnesses
python3 harness_v1.py
python3 harness_v2.py
python3 harness_v8.py
python3 harness_v10.py
```

## Output

- `results/` — Per-harness JSON results
- `diagnostic_report.md` — Consolidated markdown report with pass/fail matrix

## Acceptance Criteria

1. **D0 (Perfect):** All tests return PASS — zero false alarms
2. **D1–D9 (Defects):** Each defect detected by the correct test — zero missed detections
3. **Cross-contamination:** Each defect triggers ONLY its target test
4. **Reproducibility:** Identical results on repeated runs

## Requirements

- Python 3.10+
- NumPy, SciPy

## License

MIT
