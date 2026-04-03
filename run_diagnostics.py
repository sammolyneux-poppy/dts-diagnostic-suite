#!/usr/bin/env python3
"""
Master Diagnostic Runner — Validates the DTS Proof Verification Battery

Executes all diagnostic harnesses (V1, V2, V8, V10) against synthetic
positive and negative controls. Produces a consolidated report showing
which tests correctly detect known defects and which correctly pass
valid inputs.

Usage:
    cd "/Users/sammolyneux/Projects/RGH/Golden Proof"
    python3 verification_outputs/diagnostics/run_diagnostics.py
"""

import subprocess
import sys
import os
import json
import time
from pathlib import Path

DIAG_DIR = Path(__file__).parent
RESULTS_DIR = DIAG_DIR / "results"

HARNESSES = [
    ("V1 — Axiom Independence Logic", "harness_v1.py"),
    ("V2 — Witness Trace Encoding", "harness_v2.py"),
    ("V8 — Simulation Concordance", "harness_v8.py"),
    ("V10 — Empirical Predictions", "harness_v10.py"),
]


def run_harness(name: str, script: str) -> dict:
    """Run a single diagnostic harness and collect results."""
    script_path = DIAG_DIR / script
    result_file = RESULTS_DIR / script.replace(".py", "_result.json").replace("harness_", "")

    print(f"\n{'='*70}")
    print(f"  Running: {name}")
    print(f"  Script:  {script_path}")
    print(f"{'='*70}")

    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=300,
            cwd=str(DIAG_DIR.parent.parent)  # Golden Proof/
        )
        elapsed = time.time() - t0
        print(proc.stdout)
        if proc.stderr:
            print(f"STDERR:\n{proc.stderr}", file=sys.stderr)

        # Try to load the result JSON
        json_path = RESULTS_DIR / script.replace("harness_", "").replace(".py", "_diagnostic.json")
        if json_path.exists():
            with open(json_path) as f:
                data = json.load(f)
        else:
            data = {"error": f"Result file not found: {json_path}"}

        return {
            "harness": name,
            "script": script,
            "exit_code": proc.returncode,
            "elapsed_seconds": round(elapsed, 2),
            "results": data,
        }

    except subprocess.TimeoutExpired:
        return {
            "harness": name,
            "script": script,
            "exit_code": -1,
            "elapsed_seconds": 300,
            "results": {"error": "TIMEOUT after 300s"},
        }
    except Exception as e:
        return {
            "harness": name,
            "script": script,
            "exit_code": -1,
            "elapsed_seconds": 0,
            "results": {"error": str(e)},
        }


def extract_counts(data: dict) -> tuple:
    """Extract (total_checks, correct_checks) from any harness JSON format."""
    if not isinstance(data, dict):
        return 0, 0

    # V8 format: has explicit total_checks / total_correct
    if "total_checks" in data and "total_correct" in data:
        return data["total_checks"], data["total_correct"]

    # V1 format: tests[] with .passed and .checks[] sub-items
    if "tests" in data:
        tests = data["tests"]
        total = 0
        correct = 0
        for t in tests:
            checks = t.get("checks", [])
            for c in checks:
                total += 1
                if isinstance(c, str):
                    if "[PASS]" in c:
                        correct += 1
                elif isinstance(c, dict) and c.get("passed", False):
                    correct += 1
        if total > 0:
            return total, correct
        # Fallback: count tests themselves
        total = len(tests)
        correct = sum(1 for t in tests if t.get("passed", False))
        return total, correct

    # V2 format: diagnostics[] with .all_pass and .checks[]
    if "diagnostics" in data:
        diags = data["diagnostics"]
        # V10 format: diagnostics[] with .passed directly
        if diags and "passed" in diags[0]:
            total = len(diags)
            correct = sum(1 for d in diags if d.get("passed", False))
            return total, correct
        # V2 format: diagnostics[] with .checks[] sub-items
        total = sum(len(d.get("checks", [])) for d in diags)
        correct = sum(
            sum(1 for c in d.get("checks", []) if c.get("passed", False))
            for d in diags
        )
        if total > 0:
            return total, correct
        total = len(diags)
        correct = sum(1 for d in diags if d.get("all_pass", False))
        return total, correct

    # Fallback: use overall_passed flag
    if "overall_passed" in data:
        return 1, 1 if data["overall_passed"] else 0

    return 0, 0


def generate_report(all_results: list) -> str:
    """Generate the master diagnostic report as markdown."""
    lines = []
    lines.append("# DTS Verification Battery — Diagnostic Report")
    lines.append("")
    lines.append(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    lines.append(f"**Python:** {sys.version.split()[0]}")
    lines.append("")

    total_checks = 0
    total_correct = 0
    total_bugs = 0

    lines.append("## Summary by Harness")
    lines.append("")
    lines.append("| Harness | Exit | Time | Checks | Correct | Bugs |")
    lines.append("|---------|------|------|--------|---------|------|")

    for r in all_results:
        data = r["results"]
        checks, correct = extract_counts(data)
        bugs = checks - correct

        total_checks += checks
        total_correct += correct
        total_bugs += bugs

        status = "OK" if r["exit_code"] == 0 else f"ERR({r['exit_code']})"
        lines.append(f"| {r['harness']} | {status} | {r['elapsed_seconds']}s | {checks} | {correct} | {bugs} |")

    lines.append("")
    lines.append(f"**Total: {total_correct}/{total_checks} checks correct, {total_bugs} bugs found**")
    lines.append("")

    # Detailed results
    lines.append("## Detailed Results")
    lines.append("")

    for r in all_results:
        lines.append(f"### {r['harness']}")
        lines.append("")
        data = r["results"]

        if isinstance(data, dict) and "error" in data:
            lines.append(f"**ERROR:** {data['error']}")
            lines.append("")
            continue

        checks_count, correct_count = extract_counts(data)
        overall = data.get("all_pass", data.get("overall_passed", data.get("overall_pass", None)))
        lines.append(f"**Checks: {correct_count}/{checks_count}** | Overall: {'PASS' if overall else 'FAIL' if overall is not None else 'N/A'}")
        lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    if total_bugs == 0 and total_checks > 0:
        lines.append("**ALL DIAGNOSTICS PASS.** The verification battery correctly detects all "
                     "injected defects and produces no false alarms on valid inputs. The tests "
                     "are validated for use on the FP4 proof.")
    elif total_bugs > 0:
        lines.append(f"**{total_bugs} DIAGNOSTIC FAILURE(S).** The following tests need repair "
                     "before the verification battery can be trusted.")
    else:
        lines.append("**NO CHECKS EXECUTED.** Diagnostic harnesses may have failed to run.")

    return "\n".join(lines)


def main():
    print("=" * 70)
    print("  DTS Verification Battery — Master Diagnostic Runner")
    print("=" * 70)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = []
    for name, script in HARNESSES:
        result = run_harness(name, script)
        all_results.append(result)

    # Generate report
    report = generate_report(all_results)
    report_path = DIAG_DIR / "diagnostic_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\n{'='*70}")
    print(f"  Diagnostic report written to: {report_path}")
    print(f"{'='*70}")

    # Save consolidated JSON
    consolidated_path = RESULTS_DIR / "consolidated_results.json"
    with open(consolidated_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  Consolidated JSON: {consolidated_path}")

    # Print final summary
    print(f"\n{report.split('## Verdict')[1] if '## Verdict' in report else ''}")


if __name__ == "__main__":
    main()
