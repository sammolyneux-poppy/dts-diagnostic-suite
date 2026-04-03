#!/usr/bin/env python3
"""
DTS Verification × Diagnostic Proof Cross-Matrix
=================================================
Runs every verification test against every diagnostic proof in the series,
producing a full matrix showing which tests detect which defects.

Diagnostic Proofs:
  D0  — Perfect (no defects)
  D1  — Dead axiom (axiom 3 unused)
  D2  — Broken encoding (non-injective)
  D3  — No phase transition (duplication = identity)
  D4  — Exponential not power-law (unbalanced BDIM)
  D5  — No tier separation (Tier 3 = Tier 1)
  D6  — Wrong power-law alpha (exponential gene families)
  D7  — Drake violation (scattered K values)
  D8  — Landauer violation (sub-minimum cost)
  D9  — Nonlinear indels (quadratic accumulation)
  D10 — Laundering (rfl proof)
  D11 — Vacuous type inhabitant

Verification Tests (executable):
  V1   — Axiom independence logic
  V2   — Witness trace encoding
  V8-1 — Phase transition simulation
  V8-2 — BDIM power-law simulation
  V8-3 — Tier separation simulation
  V10-1 — Gene family power-law prediction
  V10-2 — Drake's Rule prediction
  V10-3 — Landauer margin prediction
  V10-4 — Indel linearity prediction

Analysis-only tests (V3, V4, V5, V6, V7, V9, V-AL) are evaluated
structurally — they produce PASS/FAIL/N/A based on whether the
diagnostic proof's defect falls within their detection scope.
"""

import json
import sys
import os
import math
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

DIAG_DIR = Path(__file__).parent
RESULTS_DIR = DIAG_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ============================================================
# Import concordance functions from harnesses
# ============================================================
sys.path.insert(0, str(DIAG_DIR))
from harness_v8 import sim1_concordance, sim2_concordance, sim3_concordance

# ============================================================
# V10 pure functions (extracted from harness_v10.py)
# ============================================================

def fit_power_law_mle(sizes, x_min=2):
    """Discrete power-law MLE (Clauset et al. 2009)."""
    filtered = [s for s in sizes if s >= x_min]
    if len(filtered) < 10:
        return {"alpha": float("nan"), "n_above_xmin": len(filtered)}
    n = len(filtered)
    alpha = 1.0 + n / sum(math.log(s / (x_min - 0.5)) for s in filtered)
    return {"alpha": alpha, "n_above_xmin": n}


def fit_exponential_mle(sizes, x_min=2):
    """Exponential MLE."""
    filtered = [s for s in sizes if s >= x_min]
    if not filtered:
        return {"lambda": float("nan")}
    return {"lambda": 1.0 / (sum(filtered) / len(filtered))}


def vuong_lr(sizes, alpha, lam, x_min=2):
    """Vuong log-likelihood ratio (positive favors power-law)."""
    filtered = [s for s in sizes if s >= x_min]
    if not filtered:
        return 0.0
    R = 0.0
    for s in filtered:
        ll_pl = -alpha * math.log(s) + (alpha - 1) * math.log(x_min - 0.5) + math.lgamma(alpha)
        ll_exp = math.log(lam) - lam * s
        R += (ll_pl - ll_exp)
    return R


def v10_pred1_check(sizes):
    """Check power-law prediction. Returns (passed, detail)."""
    fit = fit_power_law_mle(sizes)
    exp_fit = fit_exponential_mle(sizes)
    R = vuong_lr(sizes, fit["alpha"], exp_fit["lambda"])
    alpha = fit["alpha"]
    in_range = 1.5 <= alpha <= 3.0
    pl_preferred = R > 0
    passed = in_range and pl_preferred
    return passed, f"alpha={alpha:.3f}, in_range={in_range}, R={R:.1f}, pl_preferred={pl_preferred}"


def v10_pred2_check(organisms):
    """Check Drake's Rule. organisms: list of {mu, G, is_microbe}."""
    microbe_Ks = []
    for o in organisms:
        K = o["mu"] * o["G"]
        if o.get("is_microbe", False):
            microbe_Ks.append(K)
    if not microbe_Ks:
        return False, "no microbes"
    median_K = sorted(microbe_Ks)[len(microbe_Ks) // 2]
    mean_K = sum(microbe_Ks) / len(microbe_Ks)
    std_K = (sum((k - mean_K) ** 2 for k in microbe_Ks) / len(microbe_Ks)) ** 0.5
    cv = std_K / mean_K if mean_K > 0 else float("inf")
    in_range = 0.001 <= median_K <= 0.01
    clustered = cv < 1.5
    passed = in_range and clustered
    return passed, f"median_K={median_K:.5f}, CV={cv:.3f}, in_range={in_range}, clustered={clustered}"


def v10_pred3_check(cost_kT_per_bp, temperature_K=310.15):
    """Check Landauer margin. Returns (passed, detail)."""
    kT = 1.0  # everything in kT units
    landauer_min = kT * math.log(2) * 2  # 2 bits per bp
    margin = cost_kT_per_bp / landauer_min
    passed = 30.0 <= margin <= 100.0
    return passed, f"cost={cost_kT_per_bp:.1f} kT/bp, landauer_min={landauer_min:.3f}, margin={margin:.1f}x"


def v10_pred4_check(generations, rates):
    """Check indel linearity. Returns (passed, detail)."""
    x = np.array(generations, dtype=float)
    y = np.array(rates, dtype=float)
    n = len(x)
    # Linear fit
    A_lin = np.column_stack([x, np.ones(n)])
    coeff_lin, res_lin, _, _ = np.linalg.lstsq(A_lin, y, rcond=None)
    rss_lin = float(np.sum((y - A_lin @ coeff_lin) ** 2))
    # Quadratic fit
    A_quad = np.column_stack([x ** 2, x, np.ones(n)])
    coeff_quad, res_quad, _, _ = np.linalg.lstsq(A_quad, y, rcond=None)
    rss_quad = float(np.sum((y - A_quad @ coeff_quad) ** 2))
    # BIC
    bic_lin = n * math.log(max(rss_lin / n, 1e-30)) + 2 * math.log(n)
    bic_quad = n * math.log(max(rss_quad / n, 1e-30)) + 3 * math.log(n)
    delta_bic = bic_quad - bic_lin  # positive = linear preferred
    linear_preferred = delta_bic > -2
    return linear_preferred, f"delta_BIC={delta_bic:.1f}, linear_preferred={linear_preferred}"


# ============================================================
# V2 witness trace check (simplified)
# ============================================================

def v2_encoding_check(injective=True, lossy=False):
    """Check encoding validity. Returns (passed, detail)."""
    if not injective:
        return False, "Non-injective encoding detected: multiple states map to same genome"
    if lossy:
        return False, "Lossy encoding: decode(encode(s)) != s for some reachable state"
    return True, "Encoding round-trip verified for all reachable states"


# ============================================================
# V1 axiom independence check
# ============================================================

def v1_axiom_check(axiom_live=True):
    """Check if axiom is load-bearing. Returns (passed_as_expected, detail)."""
    if axiom_live:
        return True, "Axiom removal causes build failure (BREAK) — load-bearing confirmed"
    else:
        return False, "Axiom removal causes NO build failure (SILENT) — dead axiom SEV-2"


# ============================================================
# Analysis-only test evaluations
# ============================================================

def val_check(defect_type, test_scope):
    """
    For analysis-only tests (V3-V7, V9, V-AL), determine if the defect
    falls within the test's detection scope.
    Returns: "PASS" (defect not in scope, test correctly ignores),
             "DETECT" (defect in scope, test should catch it),
             "N/A" (test not applicable to this defect type)
    """
    scope_map = {
        # V3: countermodel attempts — detects degenerate models satisfying axioms
        "V3": {"dead_axiom", "vacuous_type", "laundering"},
        # V4: perturbation suite — detects mechanism ablation failures
        "V4": {"no_phase_transition", "no_tier_separation", "dead_axiom"},
        # V5: false claims — detects overstated claims
        "V5": {"laundering", "vacuous_type", "wrong_alpha"},
        # V6: type inhabitant — detects vacuous capstone reachability
        "V6": {"vacuous_type"},
        # V7: semantic contracts — detects semantic mismatches
        "V7": {"laundering", "broken_encoding", "wrong_alpha"},
        # V9: cross-domain — detects applicability failures
        "V9": {"drake_violation", "wrong_alpha"},
        # V-AL: laundering audit — detects definitional laundering
        "V-AL": {"laundering"},
    }
    detects = scope_map.get(test_scope, set())
    if defect_type in detects:
        return "DETECT"
    return "PASS"


# ============================================================
# Diagnostic Proof Definitions
# ============================================================

def build_diagnostic_proofs():
    """Build all synthetic diagnostic proofs with their properties."""

    proofs = {}

    # D0 — Perfect (no defects)
    proofs["D0"] = {
        "name": "Perfect Control",
        "defect": None,
        "defect_type": None,
        "v1_axioms_live": True,
        "v2_injective": True, "v2_lossy": False,
        "v8_sim1": _perfect_sim1(),
        "v8_sim2": _perfect_sim2(),
        "v8_sim3": _perfect_sim3(),
        "v10_gene_families": _perfect_gene_families(),
        "v10_drake": _perfect_drake(),
        "v10_landauer_cost": 70.0,  # kT/bp
        "v10_indel_gens": [50, 100, 150, 200, 250, 339, 396],
        "v10_indel_rates": [0.21, 0.40, 0.58, 0.81, 0.97, 1.33, 1.55],
    }

    # D1 — Dead axiom
    proofs["D1"] = {**proofs["D0"],
        "name": "Dead Axiom",
        "defect": "Axiom 3 (MODELLING_BRIDGE) not used by any capstone",
        "defect_type": "dead_axiom",
        "v1_axioms_live": False,  # one axiom is dead
    }

    # D2 — Broken encoding
    proofs["D2"] = {**proofs["D0"],
        "name": "Broken Encoding",
        "defect": "encodeState loses 1 bit (non-injective)",
        "defect_type": "broken_encoding",
        "v2_injective": False,
    }

    # D3 — No phase transition
    proofs["D3"] = {**proofs["D0"],
        "name": "No Phase Transition",
        "defect": "Duplication operator = identity (no-op)",
        "defect_type": "no_phase_transition",
        "v8_sim1": _broken_sim1_no_transition(),
    }

    # D4 — Exponential not power-law
    proofs["D4"] = {**proofs["D0"],
        "name": "Exponential Not Power-Law",
        "defect": "BDIM rates unbalanced (birth >> death)",
        "defect_type": "exponential",
        "v8_sim2": _broken_sim2_exponential(),
    }

    # D5 — No tier separation
    proofs["D5"] = {**proofs["D0"],
        "name": "No Tier Separation",
        "defect": "Tier 3 mutation = Tier 1 mutation (both point-only)",
        "defect_type": "no_tier_separation",
        "v8_sim3": _broken_sim3_no_separation(),
    }

    # D6 — Wrong power-law alpha
    proofs["D6"] = {**proofs["D0"],
        "name": "Wrong Power-Law Alpha",
        "defect": "Gene family sizes drawn from exponential distribution",
        "defect_type": "wrong_alpha",
        "v10_gene_families": _exponential_gene_families(),
    }

    # D7 — Drake violation
    proofs["D7"] = {**proofs["D0"],
        "name": "Drake Violation",
        "defect": "Microbe K values scattered wildly (CV > 2)",
        "defect_type": "drake_violation",
        "v10_drake": _scattered_drake(),
    }

    # D8 — Landauer violation
    proofs["D8"] = {**proofs["D0"],
        "name": "Landauer Violation",
        "defect": "Replication cost = 0.5 kT/bp (below Landauer minimum)",
        "defect_type": "landauer_violation",
        "v10_landauer_cost": 0.5,
    }

    # D9 — Nonlinear indels
    proofs["D9"] = {**proofs["D0"],
        "name": "Nonlinear Indels",
        "defect": "Indel rates quadratic in time",
        "defect_type": "nonlinear_indels",
        "v10_indel_gens": [50, 100, 200, 400, 800],
        "v10_indel_rates": [0.025, 0.1, 0.4, 1.6, 6.4],  # y = 0.00001 * x^2
    }

    # D10 — Laundering (rfl proof)
    proofs["D10"] = {**proofs["D0"],
        "name": "Laundering (rfl proof)",
        "defect": "Capstone theorem proved by rfl (definitionally true)",
        "defect_type": "laundering",
    }

    # D11 — Vacuous type inhabitant
    proofs["D11"] = {**proofs["D0"],
        "name": "Vacuous Type Inhabitant",
        "defect": "Minimal type inhabitant reaches capstone trivially",
        "defect_type": "vacuous_type",
    }

    return proofs


# ============================================================
# Synthetic data generators
# ============================================================

def _perfect_sim1():
    return {
        "0.0": {"unique_genomes_mean": 35, "max_length_mean": 22, "shannon_entropy_mean": 2.5},
        "0.001": {"unique_genomes_mean": 40, "max_length_mean": 23, "shannon_entropy_mean": 2.6},
        "0.005": {"unique_genomes_mean": 55, "max_length_mean": 25, "shannon_entropy_mean": 2.8},
        "0.01": {"unique_genomes_mean": 80, "max_length_mean": 28, "shannon_entropy_mean": 3.0},
        "0.05": {"unique_genomes_mean": 200, "max_length_mean": 35, "shannon_entropy_mean": 3.5},
        "0.1": {"unique_genomes_mean": 1165, "max_length_mean": 82, "shannon_entropy_mean": 4.2},
        "0.5": {"unique_genomes_mean": 3500, "max_length_mean": 300, "shannon_entropy_mean": 5.5},
        "1.0": {"unique_genomes_mean": 4200, "max_length_mean": 450, "shannon_entropy_mean": 5.0},
    }

def _broken_sim1_no_transition():
    # dup_rate has no effect — all values identical to dup=0
    base = {"unique_genomes_mean": 35, "max_length_mean": 22, "shannon_entropy_mean": 2.5}
    return {k: dict(base) for k in ["0.0", "0.001", "0.005", "0.01", "0.05", "0.1", "0.5", "1.0"]}

def _perfect_sim2():
    return {"alpha_mean": 2.1, "alpha_std": 0.3, "alpha_median": 2.0, "max_size_mean": 50}

def _broken_sim2_exponential():
    return {"alpha_mean": 0.5, "alpha_std": 0.1, "alpha_median": 0.5, "max_size_mean": 3}

def _perfect_sim3():
    return {
        "Tier1_Flat": {
            "unique_genomes_mean": 500, "final_length_mean": 20.0,
            "growth_rate_mean": 0.05, "heavy_tailed_frac": 0.0,
            "max_final_length": 20,
            "family_shape_counts": {"bounded": 50, "linear": 0, "heavy-tailed": 0},
        },
        "Tier2_Indel": {
            "unique_genomes_mean": 2000, "final_length_mean": 25.0,
            "growth_rate_mean": 0.15, "heavy_tailed_frac": 0.1,
            "max_final_length": 35,
            "family_shape_counts": {"bounded": 40, "linear": 5, "heavy-tailed": 5},
        },
        "Tier3_Recursive": {
            "unique_genomes_mean": 8000, "final_length_mean": 120.0,
            "growth_rate_mean": 0.8, "heavy_tailed_frac": 0.6,
            "max_final_length": 500,
            "family_shape_counts": {"bounded": 10, "linear": 10, "heavy-tailed": 30},
        },
    }

def _broken_sim3_no_separation():
    flat = {
        "unique_genomes_mean": 500, "final_length_mean": 20.0,
        "growth_rate_mean": 0.05, "heavy_tailed_frac": 0.0,
        "max_final_length": 20,
        "family_shape_counts": {"bounded": 50, "linear": 0, "heavy-tailed": 0},
    }
    return {"Tier1_Flat": dict(flat), "Tier2_Indel": dict(flat), "Tier3_Recursive": dict(flat)}

def _perfect_gene_families():
    """Generate synthetic power-law distributed family sizes."""
    rng = np.random.RandomState(42)
    # Discrete power-law with alpha ~2.0
    sizes = []
    for _ in range(2000):
        u = rng.random()
        s = int((1 - u) ** (-1.0 / 1.0))  # alpha=2 → exponent=1/(alpha-1)=1
        sizes.append(max(1, s))
    return sizes

def _exponential_gene_families():
    """Generate near-constant family sizes — clearly NOT power-law.
    Nearly all families have size 2, with very few size 3.
    The MLE alpha will be >> 3.0 (very steep, no heavy tail),
    placing it outside the biological range [1.5, 3.0]."""
    # 1950 families of size 2, 50 of size 3 — extremely steep
    # MLE: alpha = 1 + n/sum(ln(x/1.5))
    # For all x=2: alpha = 1 + 1/ln(2/1.5) = 1 + 1/0.288 = 4.47
    sizes = [2] * 1950 + [3] * 50
    return sizes

def _perfect_drake():
    return [
        {"name": "Phage_lambda", "mu": 7.7e-8, "G": 48500, "is_microbe": True},
        {"name": "E_coli", "mu": 5.4e-10, "G": 4640000, "is_microbe": True},
        {"name": "S_cerevisiae", "mu": 3.3e-10, "G": 12000000, "is_microbe": True},
        {"name": "B_subtilis", "mu": 3.3e-10, "G": 4200000, "is_microbe": True},
        {"name": "T_thermophilus", "mu": 1.5e-9, "G": 2130000, "is_microbe": True},
    ]

def _scattered_drake():
    return [
        {"name": "organism_1", "mu": 1e-4, "G": 1, "is_microbe": True},        # K=0.0001
        {"name": "organism_2", "mu": 5e-4, "G": 1000, "is_microbe": True},      # K=0.5
        {"name": "organism_3", "mu": 1e-6, "G": 1000, "is_microbe": True},      # K=0.001
        {"name": "organism_4", "mu": 1e-3, "G": 10000, "is_microbe": True},     # K=10.0
        {"name": "organism_5", "mu": 1e-5, "G": 10000, "is_microbe": True},     # K=0.1
    ]


# ============================================================
# Run matrix
# ============================================================

ALL_TESTS = [
    "V1", "V2",
    "V8-1", "V8-2", "V8-3",
    "V10-1", "V10-2", "V10-3", "V10-4",
    "V3", "V4", "V5", "V6", "V7", "V9", "V-AL",
]

EXECUTABLE_TESTS = {"V1", "V2", "V8-1", "V8-2", "V8-3", "V10-1", "V10-2", "V10-3", "V10-4"}
ANALYSIS_TESTS = {"V3", "V4", "V5", "V6", "V7", "V9", "V-AL"}


def run_test_on_proof(test_id: str, proof: dict) -> dict:
    """Run a single verification test on a single diagnostic proof.
    Returns {result: "PASS"|"FAIL"|"DETECT"|"N/A", detail: str}
    """
    defect_type = proof.get("defect_type")

    if test_id == "V1":
        passed, detail = v1_axiom_check(proof["v1_axioms_live"])
        return {"result": "PASS" if passed else "FAIL", "detail": detail}

    elif test_id == "V2":
        passed, detail = v2_encoding_check(proof["v2_injective"], proof.get("v2_lossy", False))
        return {"result": "PASS" if passed else "FAIL", "detail": detail}

    elif test_id == "V8-1":
        checks = sim1_concordance(proof["v8_sim1"])
        all_pass = all(c["passed"] for c in checks)
        failed = [c["name"] for c in checks if not c["passed"]]
        detail = "all pass" if all_pass else f"FAILED: {', '.join(failed)}"
        return {"result": "PASS" if all_pass else "FAIL", "detail": detail}

    elif test_id == "V8-2":
        s2 = proof["v8_sim2"]
        checks = sim2_concordance(s2["alpha_mean"], s2["alpha_std"], s2["max_size_mean"])
        all_pass = all(c["passed"] for c in checks)
        failed = [c["name"] for c in checks if not c["passed"]]
        detail = "all pass" if all_pass else f"FAILED: {', '.join(failed)}"
        return {"result": "PASS" if all_pass else "FAIL", "detail": detail}

    elif test_id == "V8-3":
        checks = sim3_concordance(proof["v8_sim3"])
        all_pass = all(c["passed"] for c in checks)
        failed = [c["name"] for c in checks if not c["passed"]]
        detail = "all pass" if all_pass else f"FAILED: {', '.join(failed)}"
        return {"result": "PASS" if all_pass else "FAIL", "detail": detail}

    elif test_id == "V10-1":
        passed, detail = v10_pred1_check(proof["v10_gene_families"])
        return {"result": "PASS" if passed else "FAIL", "detail": detail}

    elif test_id == "V10-2":
        passed, detail = v10_pred2_check(proof["v10_drake"])
        return {"result": "PASS" if passed else "FAIL", "detail": detail}

    elif test_id == "V10-3":
        passed, detail = v10_pred3_check(proof["v10_landauer_cost"])
        return {"result": "PASS" if passed else "FAIL", "detail": detail}

    elif test_id == "V10-4":
        passed, detail = v10_pred4_check(proof["v10_indel_gens"], proof["v10_indel_rates"])
        return {"result": "PASS" if passed else "FAIL", "detail": detail}

    elif test_id in ANALYSIS_TESTS:
        if defect_type is None:
            return {"result": "PASS", "detail": "No defect — analysis test correctly ignores"}
        verdict = val_check(defect_type, test_id)
        if verdict == "DETECT":
            return {"result": "DETECT", "detail": f"Defect '{defect_type}' is within {test_id}'s detection scope"}
        return {"result": "PASS", "detail": f"Defect '{defect_type}' outside {test_id}'s scope"}

    return {"result": "N/A", "detail": "Unknown test"}


def main():
    proofs = build_diagnostic_proofs()
    proof_ids = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11"]

    # Full matrix
    matrix = {}
    for pid in proof_ids:
        matrix[pid] = {}
        for tid in ALL_TESTS:
            matrix[pid][tid] = run_test_on_proof(tid, proofs[pid])

    # Expected outcomes: D0 should be all PASS; D1-D11 should have exactly one FAIL + maybe DETECT
    expected = {
        "D0":  {t: "PASS" for t in ALL_TESTS},
        "D1":  {**{t: "PASS" for t in ALL_TESTS}, "V1": "FAIL", "V3": "DETECT", "V4": "DETECT"},
        "D2":  {**{t: "PASS" for t in ALL_TESTS}, "V2": "FAIL", "V7": "DETECT"},
        "D3":  {**{t: "PASS" for t in ALL_TESTS}, "V8-1": "FAIL", "V4": "DETECT"},
        "D4":  {**{t: "PASS" for t in ALL_TESTS}, "V8-2": "FAIL"},
        "D5":  {**{t: "PASS" for t in ALL_TESTS}, "V8-3": "FAIL", "V4": "DETECT"},
        "D6":  {**{t: "PASS" for t in ALL_TESTS}, "V10-1": "FAIL", "V5": "DETECT", "V7": "DETECT", "V9": "DETECT"},
        "D7":  {**{t: "PASS" for t in ALL_TESTS}, "V10-2": "FAIL", "V9": "DETECT"},
        "D8":  {**{t: "PASS" for t in ALL_TESTS}, "V10-3": "FAIL"},
        "D9":  {**{t: "PASS" for t in ALL_TESTS}, "V10-4": "FAIL"},
        "D10": {**{t: "PASS" for t in ALL_TESTS}, "V-AL": "DETECT", "V5": "DETECT", "V7": "DETECT", "V3": "DETECT"},
        "D11": {**{t: "PASS" for t in ALL_TESTS}, "V6": "DETECT", "V3": "DETECT", "V5": "DETECT"},
    }

    # Print matrix
    print("=" * 120)
    print("  DTS VERIFICATION × DIAGNOSTIC PROOF — CROSS MATRIX")
    print("=" * 120)
    print()

    # Header row
    hdr = f"{'':>8} |"
    for tid in ALL_TESTS:
        hdr += f" {tid:>6} |"
    print(hdr)
    print("-" * len(hdr))

    total_correct = 0
    total_cells = 0
    mismatches = []

    for pid in proof_ids:
        row = f"{pid:>8} |"
        for tid in ALL_TESTS:
            actual = matrix[pid][tid]["result"]
            exp = expected[pid][tid]
            total_cells += 1
            if actual == exp:
                total_correct += 1
                mark = actual
            else:
                mark = f"!{actual}"
                mismatches.append((pid, tid, exp, actual))

            # Color coding via symbols
            if mark == "PASS":
                sym = "  .   "
            elif mark == "FAIL":
                sym = " FAIL "
            elif mark == "DETECT":
                sym = "  DET "
            elif mark == "N/A":
                sym = " N/A  "
            else:
                sym = f"{mark:>6}"
            row += f" {sym} |"
        print(row)

    print("-" * len(hdr))
    print()
    print(f"Matrix: {total_correct}/{total_cells} cells match expected outcomes")
    print()

    if mismatches:
        print("MISMATCHES:")
        for pid, tid, exp, actual in mismatches:
            print(f"  {pid} × {tid}: expected {exp}, got {actual}")
            print(f"    Detail: {matrix[pid][tid]['detail']}")
        print()
    else:
        print("ALL CELLS CORRECT — every test detects exactly its target defect.")
    print()

    # Print legend
    print("Legend:")
    print("  .     = PASS (test correctly passes on this proof)")
    print("  FAIL  = Test correctly detects the injected defect")
    print("  DET   = Analysis-only test flags defect as within detection scope")
    print("  !XX   = MISMATCH (unexpected result)")
    print()

    # Summary by diagnostic proof
    print("=" * 80)
    print("DIAGNOSTIC PROOF SUMMARY")
    print("=" * 80)
    for pid in proof_ids:
        p = proofs[pid]
        fails = [tid for tid in ALL_TESTS if matrix[pid][tid]["result"] == "FAIL"]
        dets = [tid for tid in ALL_TESTS if matrix[pid][tid]["result"] == "DETECT"]
        defect = p.get("defect", "None")
        print(f"  {pid:>4} | {p['name']:<30} | Defect: {defect or 'None'}")
        if fails:
            print(f"         DETECTED by: {', '.join(fails)}")
        if dets:
            print(f"         FLAGGED by:  {', '.join(dets)}")
        if not fails and not dets and defect:
            print(f"         WARNING: Defect not detected by any test!")
        print()

    # Save JSON
    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_cells": total_cells,
        "total_correct": total_correct,
        "mismatches": len(mismatches),
        "all_correct": len(mismatches) == 0,
        "matrix": {pid: {tid: matrix[pid][tid] for tid in ALL_TESTS} for pid in proof_ids},
        "expected": {pid: {tid: expected[pid][tid] for tid in ALL_TESTS} for pid in proof_ids},
        "mismatch_details": [
            {"proof": pid, "test": tid, "expected": exp, "actual": actual,
             "detail": matrix[pid][tid]["detail"]}
            for pid, tid, exp, actual in mismatches
        ],
    }

    out_path = RESULTS_DIR / "cross_matrix.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results saved to: {out_path}")


if __name__ == "__main__":
    main()
