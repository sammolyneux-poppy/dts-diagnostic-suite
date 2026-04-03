#!/usr/bin/env python3
"""Diagnostic harness for V1 axiom independence test.

Validates V1's logic (file backup/restore, axiom comment-out,
error classification, error extraction, dead-axiom detection)
using synthetic inputs — no Lean builds required.
"""

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")

# ---------------------------------------------------------------------------
# Re-implemented V1 pure functions (mirrors v1_test.py logic exactly)
# ---------------------------------------------------------------------------

def find_axiom_block(lines, start_line_1indexed):
    """Find the extent of a multi-line axiom declaration.
    Returns (start_idx, end_idx) as 0-indexed line indices (inclusive).
    """
    start_idx = start_line_1indexed - 1
    end_idx = start_idx

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if stripped == "":
            end_idx = i - 1
            break
        if re.match(
            r'^(theorem|lemma|def|noncomputable|axiom|structure|instance'
            r'|class|section|namespace|end |open |import |#|/--|\/-)',
            stripped,
        ):
            end_idx = i - 1
            break
        end_idx = i

    return start_idx, end_idx


def comment_out_block(lines, start_idx, end_idx):
    """Comment out lines[start_idx..end_idx] inclusive."""
    new_lines = lines.copy()
    for i in range(start_idx, end_idx + 1):
        new_lines[i] = "-- V1_DISABLED " + lines[i]
    return new_lines


def restore_block(lines, start_idx, end_idx):
    """Undo comment_out_block — strip the '-- V1_DISABLED ' prefix."""
    new_lines = lines.copy()
    prefix = "-- V1_DISABLED "
    for i in range(start_idx, end_idx + 1):
        if new_lines[i].startswith(prefix):
            new_lines[i] = new_lines[i][len(prefix):]
    return new_lines


def extract_errors(build_output):
    """Extract error lines from build output (mirrors V1 exactly)."""
    errors = []
    for line in build_output.split("\n"):
        if "error" in line.lower() and ("error:" in line or "error(" in line):
            errors.append(line.strip())
    return errors


def classify(error_count):
    """V1 classification: 0 errors -> SILENT, >0 -> BREAK."""
    return "BREAK" if error_count > 0 else "SILENT"


def extract_error_files(errors):
    """Extract unique .lean filenames from error lines (mirrors V1)."""
    error_files = set()
    for err in errors:
        if ".lean:" in err:
            ef = err.split(".lean:")[0].split("/")[-1] + ".lean"
            error_files.add(ef)
    return sorted(error_files)


# ---------------------------------------------------------------------------
# Diagnostic tests
# ---------------------------------------------------------------------------

class DiagnosticResult:
    def __init__(self, name):
        self.name = name
        self.passed = True
        self.details = []

    def check(self, description, condition, extra=""):
        status = "PASS" if condition else "FAIL"
        if not condition:
            self.passed = False
        msg = f"  [{status}] {description}"
        if extra and not condition:
            msg += f" — {extra}"
        self.details.append(msg)
        return condition

    def to_dict(self):
        return {
            "test": self.name,
            "passed": self.passed,
            "checks": self.details,
        }


def test_1_file_backup_restore():
    """Test 1: File Backup and Restore."""
    r = DiagnosticResult("Test 1: File Backup and Restore")

    original_content = "axiom foo : Nat\ntheorem bar : True := trivial\n-- comment\n"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".lean", delete=False) as tmp:
        tmp.write(original_content)
        tmp_path = tmp.name

    backup_path = tmp_path + ".v1bak"

    try:
        # Back up
        shutil.copy2(tmp_path, backup_path)
        r.check("Backup file created", os.path.exists(backup_path))

        # Modify original
        with open(tmp_path, "w") as f:
            f.write("MODIFIED CONTENT\n")

        with open(tmp_path, "r") as f:
            r.check("File was modified", f.read() != original_content)

        # Restore
        shutil.copy2(backup_path, tmp_path)

        with open(tmp_path, "r") as f:
            restored = f.read()

        r.check(
            "Restored content matches original",
            restored == original_content,
            f"got {restored!r}",
        )
    finally:
        for p in (tmp_path, backup_path):
            if os.path.exists(p):
                os.remove(p)

    return r


def test_2_axiom_comment_out():
    """Test 2: Axiom Comment-Out Pattern (single and multi-line)."""
    r = DiagnosticResult("Test 2: Axiom Comment-Out Pattern")

    # --- Single-line axiom ---
    single_lines = [
        "import Mathlib\n",
        "\n",
        "axiom test_axiom : Nat -> Nat\n",
        "\n",
        "theorem uses_it : True := trivial\n",
    ]

    s, e = find_axiom_block(single_lines, 3)  # line 3 (1-indexed)
    r.check("Single-line block start correct", s == 2, f"got {s}")
    r.check("Single-line block end correct", e == 2, f"got {e}")

    commented = comment_out_block(single_lines, s, e)
    r.check(
        "Single-line correctly commented out",
        commented[2] == "-- V1_DISABLED axiom test_axiom : Nat -> Nat\n",
        f"got {commented[2]!r}",
    )

    restored = restore_block(commented, s, e)
    r.check(
        "Single-line restore matches original",
        restored == single_lines,
        f"got {restored!r}",
    )

    # --- Multi-line axiom ---
    multi_lines = [
        "import Mathlib\n",
        "\n",
        "axiom test_multi_axiom\n",
        "  (n : Nat) (m : Nat) : n + m = m + n\n",
        "\n",
        "theorem uses_it : True := trivial\n",
    ]

    s2, e2 = find_axiom_block(multi_lines, 3)  # line 3 (1-indexed)
    r.check("Multi-line block start correct", s2 == 2, f"got {s2}")
    r.check("Multi-line block end correct", e2 == 3, f"got {e2}")

    commented2 = comment_out_block(multi_lines, s2, e2)
    r.check(
        "Multi-line line 1 commented",
        commented2[2].startswith("-- V1_DISABLED "),
        f"got {commented2[2]!r}",
    )
    r.check(
        "Multi-line line 2 commented",
        commented2[3].startswith("-- V1_DISABLED "),
        f"got {commented2[3]!r}",
    )

    restored2 = restore_block(commented2, s2, e2)
    r.check(
        "Multi-line restore matches original",
        restored2 == multi_lines,
        f"got {restored2!r}",
    )

    return r


def test_3_error_classification():
    """Test 3: Error Classification Logic."""
    r = DiagnosticResult("Test 3: Error Classification Logic")

    # 0 errors -> SILENT
    fake_clean = "Build completed successfully.\nno errors\n"
    errors_clean = extract_errors(fake_clean)
    r.check("Clean build: 0 errors extracted", len(errors_clean) == 0, f"got {len(errors_clean)}")
    r.check("Clean build: classified SILENT", classify(len(errors_clean)) == "SILENT")

    # >0 errors -> BREAK
    fake_broken = (
        "FP4/Defs.lean:42:0: error: unknown identifier 'test_axiom'\n"
        "FP4/Defs.lean:50:0: error: type mismatch\n"
        "FP4/Defs.lean:58:0: error: function expected\n"
    )
    errors_broken = extract_errors(fake_broken)
    r.check("Broken build: 3 errors extracted", len(errors_broken) == 3, f"got {len(errors_broken)}")
    r.check("Broken build: classified BREAK", classify(len(errors_broken)) == "BREAK")

    return r


def test_4_error_extraction_regex():
    """Test 4: Error Extraction Regex."""
    r = DiagnosticResult("Test 4: Error Extraction Regex")

    fake_output = (
        "info: [1/5] Building FP4.Defs\n"
        "FP4/Defs.lean:42:0: error: unknown identifier 'test_axiom'\n"
        "info: [2/5] Building FP4.Simulation\n"
        "FP4/Simulation.lean:100:12: error: type mismatch\n"
        "warning: some warning here\n"
        "Build failed.\n"
    )

    errors = extract_errors(fake_output)
    r.check("Extracted exactly 2 errors", len(errors) == 2, f"got {len(errors)}")

    files = extract_error_files(errors)
    r.check("Identified 2 error files", len(files) == 2, f"got {files}")
    r.check("Defs.lean in error files", "Defs.lean" in files, f"got {files}")
    r.check("Simulation.lean in error files", "Simulation.lean" in files, f"got {files}")

    # Verify error content
    r.check(
        "First error mentions test_axiom",
        any("test_axiom" in e for e in errors),
        f"errors={errors}",
    )
    r.check(
        "Second error mentions type mismatch",
        any("type mismatch" in e for e in errors),
        f"errors={errors}",
    )

    return r


def test_5_dead_axiom_detection():
    """Test 5: D1 Scenario -- Dead Axiom Detection."""
    r = DiagnosticResult("Test 5: D1 Scenario - Dead Axiom Detection")

    # Simulate commenting out an axiom that produces 0 build errors
    fake_silent_output = (
        "info: [1/5] Building FP4.Defs\n"
        "info: [2/5] Building FP4.Simulation\n"
        "info: [3/5] Building FP4.Main\n"
        "Build completed successfully.\n"
    )

    errors = extract_errors(fake_silent_output)
    classification = classify(len(errors))

    r.check("Dead axiom: 0 errors", len(errors) == 0, f"got {len(errors)}")
    r.check("Dead axiom: classified SILENT", classification == "SILENT")
    r.check(
        "SILENT = SEV-2 finding (axiom not load-bearing)",
        classification == "SILENT",
        "SILENT means the axiom can be removed without breaking the build",
    )

    # Contrast: a live axiom that causes breakage
    fake_break_output = (
        "FP4/Defs.lean:42:0: error: unknown identifier 'needed_axiom'\n"
        "Build failed.\n"
    )
    errors_break = extract_errors(fake_break_output)
    class_break = classify(len(errors_break))
    r.check("Live axiom: classified BREAK", class_break == "BREAK")
    r.check(
        "BREAK confirms axiom is necessary",
        class_break == "BREAK",
    )

    return r


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    print(f"V1 Diagnostic Harness -- {now}")
    print("=" * 60)

    tests = [
        test_1_file_backup_restore,
        test_2_axiom_comment_out,
        test_3_error_classification,
        test_4_error_extraction_regex,
        test_5_dead_axiom_detection,
    ]

    all_results = []
    all_passed = True

    for test_fn in tests:
        result = test_fn()
        all_results.append(result.to_dict())
        status = "PASS" if result.passed else "FAIL"
        if not result.passed:
            all_passed = False
        print(f"\n{result.name}: {status}")
        for detail in result.details:
            print(detail)

    # Summary table
    print("\n" + "=" * 60)
    print(f"{'Test':<50} {'Result':<10}")
    print("-" * 60)
    for res in all_results:
        tag = "PASS" if res["passed"] else "FAIL"
        print(f"{res['test']:<50} {tag:<10}")
    print("-" * 60)
    overall = "PASS" if all_passed else "FAIL"
    print(f"{'Overall':<50} {overall:<10}")
    print("=" * 60)

    # Write JSON results
    output = {
        "harness": "V1 Axiom Independence Diagnostic",
        "run_date": now,
        "overall_passed": all_passed,
        "tests": all_results,
    }

    out_path = os.path.join(RESULTS_DIR, "v1_diagnostic.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults written to {out_path}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
