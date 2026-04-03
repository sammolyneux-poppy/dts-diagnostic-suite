#!/usr/bin/env python3
"""
V2 Diagnostic Harness — stress-tests the V2 witness trace encoding chain
with controlled defects to verify that detection machinery works.

Diagnostics:
  D0  — Perfect Control: valid 2-symbol tag system, all checks pass
  D2  — Broken Encoding (Non-Injective): injectivity rejection + bit-flip mismatch
  D2b — Lossy Encoding: dropped bit causes mismatch detection

Run from Golden Proof root:
  python3 verification_outputs/diagnostics/harness_v2.py
"""

import json
import os
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — allow import from the V2 witness trace directory
# ---------------------------------------------------------------------------
_this_dir = os.path.dirname(os.path.abspath(__file__))
_v2_dir = os.path.normpath(os.path.join(_this_dir, "..", "V2_witness_traces"))
if _v2_dir not in sys.path:
    sys.path.insert(0, _v2_dir)

from v2_witness_trace import (
    TagEncoding,
    TagSystem,
    encode_config,
    decode_config,
    production_table,
    full_genome,
    tag_step,
    aes_simulate_step,
    run_trace,
    summarize,
)

# ===========================================================================
# Helpers
# ===========================================================================

class DiagResult:
    def __init__(self, name: str):
        self.name = name
        self.checks: list[dict] = []

    def add(self, label: str, passed: bool, detail: str = ""):
        self.checks.append({"label": label, "passed": passed, "detail": detail})

    @property
    def all_pass(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "diagnostic": self.name,
            "all_pass": self.all_pass,
            "checks": self.checks,
        }


def print_table(results: list[DiagResult]):
    """Print a compact PASS/FAIL table."""
    col_w = 62
    print()
    print("=" * (col_w + 12))
    print(f"{'CHECK':<{col_w}} {'RESULT':>8}")
    print("-" * (col_w + 12))
    for dr in results:
        print(f"  [{dr.name}]")
        for c in dr.checks:
            tag = "PASS" if c["passed"] else "FAIL"
            label = c["label"]
            if len(label) > col_w - 4:
                label = label[: col_w - 7] + "..."
            print(f"    {label:<{col_w - 4}} [{tag:>4}]")
    print("=" * (col_w + 12))
    overall = all(dr.all_pass for dr in results)
    print(f"OVERALL: {'ALL DIAGNOSTICS PASS' if overall else 'SOME DIAGNOSTICS FAILED'}")
    print()


# ===========================================================================
# D0 — Perfect Control
# ===========================================================================

def diag_d0() -> DiagResult:
    """2-symbol tag system {a->b, b->a}, halt after 3 steps via length exhaustion."""
    dr = DiagResult("D0 — Perfect Control")

    enc = TagEncoding(block_size=2, encode_map={
        "a": [False, True],   # 01
        "b": [True, False],   # 10
    })
    ts = TagSystem(
        name="D0-control",
        alphabet=["a", "b"],
        halt_symbols=set(),
        productions={"a": ["b"], "b": ["a"]},
        encoding=enc,
    )
    # With deletion=2 and production length=1, config shrinks by 1 each step.
    # [a, b, a] (len 3) -> [a] + [b] = [a, b] (len 2) -> [] + [a] = [a] (len 1) -> halt (< 2)
    initial = ["a", "b", "a"]

    results = run_trace(ts, initial, max_steps=10)

    # Check 1: all decode matches
    all_match = all(r["match"] for r in results)
    dr.add("All decode matches", all_match)

    # Check 2: all round-trip ok
    all_rt = all(r["roundtrip_ok"] for r in results)
    dr.add("All round-trip ok", all_rt)

    # Check 3: all AES genome matches expected
    all_aes = all(r.get("aes_genome_matches_expected", True) for r in results)
    dr.add("All AES genome matches expected", all_aes)

    # Check 4: halted within 3 active steps (step indices 0..2 compute, step 2 or 3 halts)
    halted = results[-1].get("halted", False)
    dr.add("Trace halted", halted)

    # Check 5: trace length is sensible (should be 3 or 4 entries)
    dr.add(f"Trace length = {len(results)} (expect 3-4)", 2 <= len(results) <= 4)

    return dr


# ===========================================================================
# D2 — Broken Encoding (Non-Injective)
# ===========================================================================

def diag_d2() -> DiagResult:
    dr = DiagResult("D2 — Broken Encoding (Non-Injective)")

    # ---- Part A: constructor rejects non-injective map ----
    caught = False
    try:
        TagEncoding(block_size=2, encode_map={
            "a": [True, False],
            "b": [True, False],  # same as 'a' — non-injective
        })
    except AssertionError:
        caught = True
    dr.add("TagEncoding rejects non-injective map", caught)

    # ---- Part B: subtle defect — bit-flip in encoded config before AES ----
    # Build a valid system first
    enc = TagEncoding(block_size=2, encode_map={
        "a": [False, False],
        "b": [False, True],
        "H": [True, True],
    })
    ts = TagSystem(
        name="D2-bitflip",
        alphabet=["a", "b", "H"],
        halt_symbols={"H"},
        productions={"a": ["b", "H"], "b": ["a"], "H": []},
        encoding=enc,
    )
    initial = ["a", "a", "a"]

    # Compute the correct genome, then corrupt 1 bit in the tag-string portion
    genome = full_genome(ts, enc, initial)
    table = production_table(ts, enc)
    table_len = len(table)

    # Flip the first bit of the tag portion
    corrupted_genome = list(genome)
    flip_idx = table_len  # first bit of tag string
    corrupted_genome[flip_idx] = not corrupted_genome[flip_idx]

    # Run AES on the corrupted genome
    aes_result = aes_simulate_step(ts, enc, corrupted_genome)

    if aes_result is None:
        # AES couldn't even decode head — that counts as detection
        dr.add("Bit-flip detected (AES returned None)", True)
    else:
        new_genome, head_sym, details = aes_result
        # The next tag config from a correct step
        next_config = tag_step(ts, initial)
        expected_genome = full_genome(ts, enc, next_config)
        mismatch_detected = (new_genome != expected_genome)
        dr.add("Bit-flip detected (genome mismatch)", mismatch_detected,
               f"head_sym={head_sym}, extracted_matches={details['extracted_matches']}")

    return dr


# ===========================================================================
# D2b — Lossy Encoding (dropped bit)
# ===========================================================================

def diag_d2b() -> DiagResult:
    dr = DiagResult("D2b — Lossy Encoding (dropped bit)")

    enc = TagEncoding(block_size=2, encode_map={
        "a": [False, False],
        "b": [False, True],
        "c": [True, False],
    })
    ts = TagSystem(
        name="D2b-lossy",
        alphabet=["a", "b", "c"],
        halt_symbols=set(),
        productions={"a": ["b", "c"], "b": ["a"], "c": ["a", "a", "a"]},
        encoding=enc,
    )
    initial = ["a", "a", "a"]

    genome = full_genome(ts, enc, initial)
    table = production_table(ts, enc)
    table_len = len(table)

    # Drop 1 bit from the tag portion (remove the second bit of tag string)
    tag_bits = genome[table_len:]
    if len(tag_bits) >= 2:
        corrupted_tag = tag_bits[:1] + tag_bits[2:]  # drop index 1
    else:
        corrupted_tag = []

    corrupted_genome = genome[:table_len] + corrupted_tag

    aes_result = aes_simulate_step(ts, enc, corrupted_genome)

    if aes_result is None:
        dr.add("Dropped bit detected (AES returned None)", True)
    else:
        new_genome, head_sym, details = aes_result
        next_config = tag_step(ts, initial)
        expected_genome = full_genome(ts, enc, next_config)
        mismatch = (new_genome != expected_genome)
        dr.add("Dropped bit detected (genome mismatch)", mismatch,
               f"head_sym={head_sym}")

    return dr


# ===========================================================================
# Main
# ===========================================================================

def main():
    diagnostics = [diag_d0, diag_d2, diag_d2b]
    results: list[DiagResult] = []

    for fn in diagnostics:
        dr = fn()
        results.append(dr)

    print_table(results)

    # Write JSON results
    out_dir = os.path.normpath(os.path.join(_this_dir, "results"))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "v2_diagnostic.json")

    payload = {
        "harness": "harness_v2.py",
        "diagnostics": [dr.to_dict() for dr in results],
        "overall_pass": all(dr.all_pass for dr in results),
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Results written to: {out_path}")


if __name__ == "__main__":
    main()
