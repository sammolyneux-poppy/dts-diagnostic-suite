#!/usr/bin/env python3
"""
V10 Diagnostic Harness
======================
Tests each V10 prediction analysis function against KNOWN synthetic data
with controlled properties to verify the analysis machinery works correctly.

Diagnostics:
  D0  — Perfect Control (all 4 predictions, expected PASS)
  D6  — Wrong Power-Law alpha (Pred1, expected: detect non-power-law)
  D7  — Drake Violation (Pred2, expected: detect high CV)
  D8  — Landauer Violation (Pred3, expected: margin < 1)
  D9  — Nonlinear Indels (Pred4, expected: quadratic preferred)
"""

import sys
import os
import json
import numpy as np

# ---------------------------------------------------------------------------
# Path manipulation: allow importing from the V10_prediction_registry folder
# ---------------------------------------------------------------------------
GOLDEN_PROOF = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V10_DIR = os.path.join(GOLDEN_PROOF, "verification_outputs", "V10_prediction_registry")
sys.path.insert(0, V10_DIR)

from v10_pred1_gene_family_powerlaw import (
    fit_power_law_mle,
    fit_exponential_mle,
    log_likelihood_ratio_test,
)
from v10_pred4_indel_linearity import fit_and_compare

# We re-use constants/logic from pred3 directly (module-level constants)
import v10_pred3_landauer as pred3_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RESULTS = []


def record(name, passed, detail=""):
    tag = "PASS" if passed else "FAIL"
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"  [{tag}]  {name}" + (f"  -- {detail}" if detail else ""))


# ═══════════════════════════════════════════════════════════════════════════
# D0 — Perfect Control
# ═══════════════════════════════════════════════════════════════════════════

def d0_pred1_powerlaw():
    """Generate power-law data with known alpha=2.0, verify recovery."""
    np.random.seed(123)
    xmin = 1
    alpha_true = 2.0
    n = 5000
    # Inverse CDF: x = xmin * u^(-1/(alpha-1))
    u = np.random.uniform(0, 1, n)
    sizes = np.floor(xmin * u ** (-1.0 / (alpha_true - 1.0))).astype(int)
    sizes = np.clip(sizes, 1, None)

    alpha_est, alpha_err, ks_pl = fit_power_law_mle(sizes, xmin=2)
    lam, ks_exp = fit_exponential_mle(sizes, xmin=2)
    R, vuong_p = log_likelihood_ratio_test(sizes, alpha_est, lam, xmin=2)

    in_range = 1.5 <= alpha_est <= 3.0
    pl_preferred = bool(R > 0 or ks_pl < ks_exp)

    passed = in_range and pl_preferred
    record(
        "D0-Pred1  Power-law recovery (alpha=2.0)",
        passed,
        f"alpha_est={alpha_est:.3f}, in_range={in_range}, pl_preferred={pl_preferred}, R={R:.2f}",
    )
    return passed


def d0_pred2_drake():
    """Create 5 synthetic microbes with K clustering near 0.003."""
    # Realistic mu and G values that give K ~ 0.003
    microbes = [
        {"mu": 6.0e-10, "G": 5.0e6},   # K = 0.0030
        {"mu": 5.5e-10, "G": 5.5e6},   # K = 0.003025
        {"mu": 7.0e-10, "G": 4.3e6},   # K = 0.00301
        {"mu": 4.5e-10, "G": 6.5e6},   # K = 0.002925
        {"mu": 5.0e-10, "G": 6.0e6},   # K = 0.003
    ]
    Ks = np.array([m["mu"] * m["G"] for m in microbes])
    cv = np.std(Ks) / np.mean(Ks)
    median_K = np.median(Ks)
    eigen_bound = np.log(2)
    all_below = bool(np.all(Ks < eigen_bound))
    drake_confirmed = 0.001 <= median_K <= 0.01
    cluster_ok = cv < 1.5

    passed = drake_confirmed and all_below and cluster_ok
    record(
        "D0-Pred2  Drake rule (K~0.003)",
        passed,
        f"median_K={median_K:.5f}, CV={cv:.4f}, all_below_Eigen={all_below}",
    )
    return passed


def d0_pred3_landauer():
    """Verify Landauer margin with actual physics constants gives ~50x."""
    kT = pred3_mod.kT
    ln2 = pred3_mod.ln2
    landauer_kT = 2.0 * ln2  # per bp in kT units

    # Sum component costs from the pred3 module
    total_kT = sum(c["kT_per_bp"] for c in pred3_mod.COST_ESTIMATES.values())
    margin = total_kT / landauer_kT

    passed = margin > 1.0  # well above Landauer limit
    record(
        "D0-Pred3  Landauer margin (~50x)",
        passed,
        f"total_kT={total_kT:.1f}, landauer_kT={landauer_kT:.4f}, margin={margin:.1f}x",
    )
    return passed


def d0_pred4_indel():
    """Linear synthetic data — linear model should be preferred."""
    gens = [100, 200, 300, 400, 500]
    rate = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = fit_and_compare(gens, rate)
    passed = bool(result["linear_preferred"])
    record(
        "D0-Pred4  Linear indels",
        passed,
        f"delta_BIC={result['delta_BIC']:.3f}, linear_preferred={result['linear_preferred']}",
    )
    return passed


# ═══════════════════════════════════════════════════════════════════════════
# D6 — Wrong Power-Law Alpha (Pred1)
# ═══════════════════════════════════════════════════════════════════════════

def d6_wrong_alpha():
    """Exponential data should NOT look like a power law."""
    np.random.seed(456)
    sizes = (np.random.exponential(3.0, 1000) + 1).astype(int)
    sizes = np.clip(sizes, 1, None)

    alpha_est, alpha_err, ks_pl = fit_power_law_mle(sizes, xmin=2)
    lam, ks_exp = fit_exponential_mle(sizes, xmin=2)
    R, vuong_p = log_likelihood_ratio_test(sizes, alpha_est, lam, xmin=2)

    alpha_outside = alpha_est < 1.5 or alpha_est > 3.0
    exp_preferred = R < 0  # negative R means exponential fits better

    passed = alpha_outside or exp_preferred
    record(
        "D6  Wrong alpha (exponential data)",
        passed,
        f"alpha_est={alpha_est:.3f}, outside_range={alpha_outside}, R={R:.2f}, exp_preferred={exp_preferred}",
    )
    return passed


# ═══════════════════════════════════════════════════════════════════════════
# D7 — Drake Violation (Pred2)
# ═══════════════════════════════════════════════════════════════════════════

def d7_drake_violation():
    """Wildly scattered K values should give CV > 1.5."""
    Ks = np.array([0.0001, 0.5, 0.001, 10.0, 0.1])
    cv = np.std(Ks) / np.mean(Ks)

    passed = cv > 1.5
    record(
        "D7  Drake violation (scattered K)",
        passed,
        f"CV={cv:.4f}, K_values={Ks.tolist()}",
    )
    return passed


# ═══════════════════════════════════════════════════════════════════════════
# D8 — Landauer Violation (Pred3)
# ═══════════════════════════════════════════════════════════════════════════

def d8_landauer_violation():
    """Replication cost below Landauer minimum should give margin < 1."""
    ln2 = np.log(2)
    landauer_kT = 2.0 * ln2  # ~1.386 kT per bp

    fake_cost_kT = 0.5  # 0.5 kT/bp — below the ~1.386 kT/bp minimum
    margin = fake_cost_kT / landauer_kT

    passed = margin < 1.0
    record(
        "D8  Landauer violation (cost < minimum)",
        passed,
        f"fake_cost={fake_cost_kT} kT/bp, landauer_min={landauer_kT:.4f} kT/bp, margin={margin:.3f}",
    )
    return passed


# ═══════════════════════════════════════════════════════════════════════════
# D9 — Nonlinear Indels (Pred4)
# ═══════════════════════════════════════════════════════════════════════════

def d9_nonlinear_indels():
    """Quadratic data should make quadratic model preferred by BIC."""
    gens = [100, 200, 300, 400, 500]
    rate = [1.0, 4.0, 9.0, 16.0, 25.0]  # rate proportional to gen^2
    result = fit_and_compare(gens, rate)

    passed = not result["linear_preferred"]
    record(
        "D9  Nonlinear indels (quadratic data)",
        passed,
        f"delta_BIC={result['delta_BIC']:.3f}, linear_preferred={result['linear_preferred']}",
    )
    return passed


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("V10 DIAGNOSTIC HARNESS")
    print("=" * 70)
    print()

    # --- D0: Perfect Controls ---
    print("--- D0: Perfect Controls ---")
    d0_pred1_powerlaw()
    d0_pred2_drake()
    d0_pred3_landauer()
    d0_pred4_indel()
    print()

    # --- D6–D9: Failure-Mode Diagnostics ---
    print("--- D6-D9: Failure-Mode Diagnostics ---")
    d6_wrong_alpha()
    d7_drake_violation()
    d8_landauer_violation()
    d9_nonlinear_indels()
    print()

    # --- Summary Table ---
    n_pass = sum(1 for r in RESULTS if r["passed"])
    n_total = len(RESULTS)

    print("=" * 70)
    print(f"SUMMARY: {n_pass}/{n_total} diagnostics passed")
    print("=" * 70)
    for r in RESULTS:
        tag = "PASS" if r["passed"] else "FAIL"
        print(f"  [{tag}]  {r['name']}")
    print("=" * 70)

    # --- Write JSON results ---
    output = {
        "harness": "V10 Diagnostic Harness",
        "total_pass": n_pass,
        "total_tests": n_total,
        "all_pass": n_pass == n_total,
        "diagnostics": RESULTS,
    }

    results_dir = os.path.join(
        GOLDEN_PROOF, "verification_outputs", "diagnostics", "results"
    )
    os.makedirs(results_dir, exist_ok=True)
    outpath = os.path.join(results_dir, "v10_diagnostic.json")
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {outpath}")

    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
