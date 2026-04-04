"""
V8 Diagnostic Harness
=====================
Tests each simulation's concordance checks against KNOWN synthetic data.
No full simulations are re-run; instead we inject pre-computed result dicts
that should deterministically PASS or FAIL specific concordance checks.

Scenarios:
  D0 — Perfect Control:       all checks should PASS (all 3 sims)
  D3 — No Phase Transition:   Sim1 tests 2,4 should FAIL
  D4 — Exponential Not PL:    Sim2 test 1 should FAIL
  D5 — No Tier Separation:    Sim3 tests 5,7,8 should FAIL

Usage:
  cd "/Users/sammolyneux/Projects/RGH/Golden Proof"
  python3 verification_outputs/diagnostics/harness_v8.py
"""

import json
import os
import sys

# ============================================================
# Sim1 concordance logic (extracted from v8_sim1_phase_transition.py)
# ============================================================

def sim1_concordance(results: dict, initial_length: int = 20) -> list:
    """
    Re-implements the 5 concordance checks from Sim1.
    results: dict keyed by dup_rate string, each with:
      unique_genomes_mean, max_length_mean, shannon_entropy_mean, etc.
    Returns list of {name, passed, detail}.
    """
    checks = []

    r0 = results["0.0"]
    r1 = results["1.0"]
    r_low = results["0.05"]
    r_high = results["0.1"]
    r_mid = results["0.5"]

    # Test 1: dup_rate=0 has bounded unique genomes
    bounded = r0["unique_genomes_mean"] < 5000
    checks.append({
        "name": "sim1_t1_bounded_at_dup0",
        "passed": bounded,
        "detail": f"unique_genomes={r0['unique_genomes_mean']:.0f} (expect < 5000)",
    })

    # Test 2: dup_rate>=0.1 has significantly more unique genomes than dup_rate=0
    expansion = r_high["unique_genomes_mean"] > r0["unique_genomes_mean"] * 5
    checks.append({
        "name": "sim1_t2_expansion_at_dup01",
        "passed": expansion,
        "detail": f"dup0.1={r_high['unique_genomes_mean']:.0f} vs dup0.0={r0['unique_genomes_mean']:.0f} (need 5x)",
    })

    # Test 3: Max genome length grows with duplication
    length_growth = r_high["max_length_mean"] > r0["max_length_mean"] * 2
    checks.append({
        "name": "sim1_t3_length_growth",
        "passed": length_growth,
        "detail": f"max_len(0.1)={r_high['max_length_mean']:.0f} vs max_len(0.0)={r0['max_length_mean']:.0f} (need 2x)",
    })

    # Test 4: Phase transition between 0.05 and 0.1
    phase_jump = r_high["max_length_mean"] > r_low["max_length_mean"] * 2
    checks.append({
        "name": "sim1_t4_phase_transition",
        "passed": phase_jump,
        "detail": f"max_len(0.1)={r_high['max_length_mean']:.0f} vs max_len(0.05)={r_low['max_length_mean']:.0f} (need 2x)",
    })

    # Test 5: Entropy peaks at intermediate duplication rates
    entropy_peak = r_mid["shannon_entropy_mean"] > r0["shannon_entropy_mean"]
    checks.append({
        "name": "sim1_t5_entropy_peak",
        "passed": entropy_peak,
        "detail": f"H(0.5)={r_mid['shannon_entropy_mean']:.2f} vs H(0.0)={r0['shannon_entropy_mean']:.2f}",
    })

    return checks


# ============================================================
# Sim2 concordance logic (extracted from v8_sim2_bdim_powerlaw.py)
# ============================================================

def sim2_concordance(alpha_mean: float, alpha_std: float,
                     max_size_mean: float) -> list:
    """
    Re-implements the 4 concordance checks from Sim2.
    Returns list of {name, passed, detail}.
    """
    checks = []

    # Test 1: Pareto tail with alpha > 1
    pareto_tail = alpha_mean > 1.0
    checks.append({
        "name": "sim2_t1_pareto_tail",
        "passed": pareto_tail,
        "detail": f"alpha_mean={alpha_mean:.2f} (expect > 1.0)",
    })

    # Test 2: Alpha finite (not degenerate)
    finite_alpha = alpha_mean < 10.0
    checks.append({
        "name": "sim2_t2_alpha_finite",
        "passed": finite_alpha,
        "detail": f"alpha_mean={alpha_mean:.2f} (expect < 10.0)",
    })

    # Test 3: Consistent across replicates (std < 2)
    consistent = alpha_std < 2.0
    checks.append({
        "name": "sim2_t3_consistent",
        "passed": consistent,
        "detail": f"alpha_std={alpha_std:.2f} (expect < 2.0)",
    })

    # Test 4: Heavy-tailed family sizes
    heavy = max_size_mean > 5
    checks.append({
        "name": "sim2_t4_heavy_tailed",
        "passed": heavy,
        "detail": f"max_size_mean={max_size_mean:.1f} (expect > 5)",
    })

    return checks


# ============================================================
# Sim3 concordance logic (extracted from v8_sim3_tier_separation.py)
# ============================================================

def sim3_concordance(tier_results: dict, initial_length: int = 20,
                     n_replicates: int = 50) -> list:
    """
    Re-implements the 8 concordance checks from Sim3.
    tier_results: dict with keys "Tier1_Flat", "Tier2_Indel", "Tier3_Recursive",
      each having: unique_genomes_mean, final_length_mean, max_final_length,
                   growth_rate_mean, family_shape_counts.
    Returns list of {name, passed, detail}.
    """
    checks = []

    t1 = tier_results["Tier1_Flat"]
    t2 = tier_results["Tier2_Indel"]
    t3 = tier_results["Tier3_Recursive"]

    # Test 1: Flat mutation preserves genome length
    flat_bounded = t1["final_length_mean"] == initial_length
    checks.append({
        "name": "sim3_t1_flat_length_preserved",
        "passed": flat_bounded,
        "detail": f"final_len={t1['final_length_mean']:.0f} (expect {initial_length})",
    })

    # Test 2: Indel < Recursive in length
    indel_linear = t2["final_length_mean"] < t3["final_length_mean"]
    checks.append({
        "name": "sim3_t2_indel_lt_recursive_length",
        "passed": indel_linear,
        "detail": f"Tier2={t2['final_length_mean']:.0f} vs Tier3={t3['final_length_mean']:.0f}",
    })

    # Test 3: Recursive max length > Flat max length
    recursive_largest = t3["max_final_length"] > t1["max_final_length"]
    checks.append({
        "name": "sim3_t3_recursive_max_gt_flat",
        "passed": recursive_largest,
        "detail": f"Tier3_max={t3['max_final_length']} vs Tier1_max={t1['max_final_length']}",
    })

    # Test 4: Flat state space bounded (< 2^initial_length)
    flat_ss_bounded = t1["unique_genomes_mean"] < 2 ** initial_length
    checks.append({
        "name": "sim3_t4_flat_statespace_bounded",
        "passed": flat_ss_bounded,
        "detail": f"Tier1_unique={t1['unique_genomes_mean']:.0f} < {2**initial_length}",
    })

    # Test 5: Recursive accesses genome lengths unreachable by Flat (>5x)
    recursive_longer = t3["max_final_length"] > t1["max_final_length"] * 5
    checks.append({
        "name": "sim3_t5_recursive_longer_than_flat",
        "passed": recursive_longer,
        "detail": f"T3 max={t3['max_final_length']} vs T1 max={t1['max_final_length']}",
    })

    # Test 6: Length ordering Flat <= Indel <= Recursive
    length_ordering = (t1["final_length_mean"] <= t2["final_length_mean"] <=
                       t3["final_length_mean"])
    checks.append({
        "name": "sim3_t6_length_ordering",
        "passed": length_ordering,
        "detail": (f"Flat={t1['final_length_mean']:.0f} <= "
                   f"Indel={t2['final_length_mean']:.0f} <= "
                   f"Recursive={t3['final_length_mean']:.0f}"),
    })

    # Test 7: Recursive mean length >> Flat (complexity growth, >3x)
    recursive_complex = t3["final_length_mean"] > t1["final_length_mean"] * 3
    checks.append({
        "name": "sim3_t7_recursive_complexity",
        "passed": recursive_complex,
        "detail": f"T3 mean_len={t3['final_length_mean']:.0f} vs T1={t1['final_length_mean']:.0f}",
    })

    # Test 8: Strict separation: T3 max length > 10× T1
    strict_sep = t3["max_final_length"] > t1["max_final_length"] * 10
    checks.append({
        "name": "sim3_t8_strict_separation",
        "passed": strict_sep,
        "detail": (f"T3 max={t3['max_final_length']} > "
                   f"10x T1 max={t1['max_final_length']}"),
    })

    return checks


# ============================================================
# Synthetic data factories
# ============================================================

def make_sim1_d0_perfect():
    """D0 perfect control: all Sim1 checks should PASS."""
    return {
        "0.0":  {"unique_genomes_mean": 100,  "max_length_mean": 20,   "shannon_entropy_mean": 0.5},
        "0.05": {"unique_genomes_mean": 300,  "max_length_mean": 30,   "shannon_entropy_mean": 1.0},
        "0.1":  {"unique_genomes_mean": 2000, "max_length_mean": 200,  "shannon_entropy_mean": 2.5},
        "0.5":  {"unique_genomes_mean": 5000, "max_length_mean": 400,  "shannon_entropy_mean": 3.0},
        "1.0":  {"unique_genomes_mean": 8000, "max_length_mean": 500,  "shannon_entropy_mean": 1.5},
    }


def make_sim2_d0_perfect():
    """D0 perfect control: all Sim2 checks should PASS."""
    return {"alpha_mean": 2.0, "alpha_std": 0.3, "max_size_mean": 50.0}


def make_sim3_d0_perfect():
    """D0 perfect control: all Sim3 checks should PASS."""
    return {
        "Tier1_Flat": {
            "final_length_mean": 20.0,
            "max_final_length": 20,
            "unique_genomes_mean": 500.0,
            "growth_rate_mean": 0.01,
            "family_shape_counts": {"bounded": 40, "linear": 10},
        },
        "Tier2_Indel": {
            "final_length_mean": 50.0,
            "max_final_length": 80,
            "unique_genomes_mean": 3000.0,
            "growth_rate_mean": 0.10,
            "family_shape_counts": {"linear": 30, "heavy-tailed": 20},
        },
        "Tier3_Recursive": {
            "final_length_mean": 200.0,
            "max_final_length": 600,
            "unique_genomes_mean": 8000.0,
            "growth_rate_mean": 0.50,
            "family_shape_counts": {"heavy-tailed": 40, "linear": 10},
        },
    }


def make_sim1_d3_no_phase_transition():
    """D3: dup_rate=0.0 and dup_rate=0.1 have IDENTICAL metrics.
    Expect: test 2 (expansion) FAIL, test 4 (phase transition) FAIL."""
    return {
        "0.0":  {"unique_genomes_mean": 100, "max_length_mean": 20, "shannon_entropy_mean": 0.5},
        "0.05": {"unique_genomes_mean": 100, "max_length_mean": 20, "shannon_entropy_mean": 0.5},
        "0.1":  {"unique_genomes_mean": 100, "max_length_mean": 20, "shannon_entropy_mean": 0.5},
        "0.5":  {"unique_genomes_mean": 100, "max_length_mean": 20, "shannon_entropy_mean": 1.0},
        "1.0":  {"unique_genomes_mean": 100, "max_length_mean": 20, "shannon_entropy_mean": 0.5},
    }


def make_sim2_d4_exponential():
    """D4: alpha_mean=0.5 (below 1.0). Expect: test 1 FAIL."""
    return {"alpha_mean": 0.5, "alpha_std": 0.3, "max_size_mean": 50.0}


def make_sim3_d5_no_separation():
    """D5: Tier 3 metrics identical to Tier 1.
    Expect: tests 5,7,8 FAIL."""
    return {
        "Tier1_Flat": {
            "final_length_mean": 20.0,
            "max_final_length": 20,
            "unique_genomes_mean": 500.0,
            "growth_rate_mean": 0.01,
            "family_shape_counts": {"bounded": 40, "linear": 10},
        },
        "Tier2_Indel": {
            "final_length_mean": 20.0,
            "max_final_length": 20,
            "unique_genomes_mean": 500.0,
            "growth_rate_mean": 0.01,
            "family_shape_counts": {"bounded": 40, "linear": 10},
        },
        "Tier3_Recursive": {
            "final_length_mean": 20.0,
            "max_final_length": 20,
            "unique_genomes_mean": 500.0,
            "growth_rate_mean": 0.01,
            "family_shape_counts": {"bounded": 40, "linear": 10},
        },
    }


# ============================================================
# Scenario runner
# ============================================================

def run_scenario(name: str, checks: list, expected_failures: set) -> dict:
    """
    Run a scenario and verify that expected checks pass/fail correctly.
    Returns scenario result dict.
    """
    scenario = {"scenario": name, "checks": [], "meta_pass": True}

    for c in checks:
        cname = c["name"]
        should_fail = cname in expected_failures
        expected_pass = not should_fail

        meta_ok = (c["passed"] == expected_pass)
        if not meta_ok:
            scenario["meta_pass"] = False

        scenario["checks"].append({
            "name": cname,
            "concordance_result": "PASS" if c["passed"] else "FAIL",
            "expected": "FAIL" if should_fail else "PASS",
            "diagnostic_ok": meta_ok,
            "detail": c["detail"],
        })

    return scenario


# ============================================================
# Main
# ============================================================

def main():
    all_scenarios = []

    # ---- D0: Perfect Control ----

    # Sim1 D0
    checks = sim1_concordance(make_sim1_d0_perfect())
    all_scenarios.append(run_scenario("D0_sim1_perfect", checks, expected_failures=set()))

    # Sim2 D0
    d = make_sim2_d0_perfect()
    checks = sim2_concordance(d["alpha_mean"], d["alpha_std"], d["max_size_mean"])
    all_scenarios.append(run_scenario("D0_sim2_perfect", checks, expected_failures=set()))

    # Sim3 D0
    checks = sim3_concordance(make_sim3_d0_perfect())
    all_scenarios.append(run_scenario("D0_sim3_perfect", checks, expected_failures=set()))

    # ---- D3: No Phase Transition (Sim1) ----
    checks = sim1_concordance(make_sim1_d3_no_phase_transition())
    all_scenarios.append(run_scenario(
        "D3_sim1_no_phase_transition", checks,
        expected_failures={"sim1_t2_expansion_at_dup01", "sim1_t3_length_growth",
                           "sim1_t4_phase_transition"},
    ))

    # ---- D4: Exponential Not Power-Law (Sim2) ----
    d = make_sim2_d4_exponential()
    checks = sim2_concordance(d["alpha_mean"], d["alpha_std"], d["max_size_mean"])
    all_scenarios.append(run_scenario(
        "D4_sim2_exponential", checks,
        expected_failures={"sim2_t1_pareto_tail"},
    ))

    # ---- D5: No Tier Separation (Sim3) ----
    checks = sim3_concordance(make_sim3_d5_no_separation())
    all_scenarios.append(run_scenario(
        "D5_sim3_no_separation", checks,
        expected_failures={"sim3_t2_indel_lt_recursive_length",
                           "sim3_t3_recursive_max_gt_flat",
                           "sim3_t5_recursive_longer_than_flat",
                           "sim3_t7_recursive_complexity",
                           "sim3_t8_strict_separation"},
    ))

    # ---- Print Results ----
    print("=" * 78)
    print("V8 DIAGNOSTIC HARNESS — RESULTS")
    print("=" * 78)

    total_diag = 0
    total_ok = 0

    for sc in all_scenarios:
        meta = "OK" if sc["meta_pass"] else "MISMATCH"
        print(f"\n  Scenario: {sc['scenario']}  [{meta}]")
        print(f"  {'Check':<42} {'Got':<6} {'Exp':<6} {'Diag'}")
        print(f"  {'-'*42} {'-'*6} {'-'*6} {'-'*6}")
        for c in sc["checks"]:
            total_diag += 1
            diag_str = "ok" if c["diagnostic_ok"] else "WRONG"
            if c["diagnostic_ok"]:
                total_ok += 1
            print(f"  {c['name']:<42} {c['concordance_result']:<6} "
                  f"{c['expected']:<6} {diag_str}")

    print()
    print("=" * 78)
    all_pass = total_ok == total_diag
    verdict = "ALL DIAGNOSTICS CORRECT" if all_pass else "SOME DIAGNOSTICS WRONG"
    print(f"  {verdict}: {total_ok}/{total_diag} checks matched expectations")
    print("=" * 78)

    # ---- Write JSON ----
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "v8_diagnostic.json")

    output = {
        "harness": "harness_v8",
        "total_checks": total_diag,
        "total_correct": total_ok,
        "all_pass": all_pass,
        "scenarios": all_scenarios,
    }
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Results written to {out_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
