/-
  V2 Lean Cross-Check — Exercises the SAME tag systems as v2_witness_trace.py
  using the ACTUAL Lean definitions from FP4/TagSystem.lean and FP4/Simulation.lean.

  Run with:
    cd "Golden Proof"
    lake env lean verification_outputs/diagnostics/V2LeanCrossCheck.lean

  Compare output against:
    verification_outputs/V2_witness_traces/V2_WITNESS_TRACE_MACHINE_{1,2,3}.md

  Any disagreement between Lean and Python is a SEV-1 finding.
-/
import FP4.Simulation
import Mathlib.Tactic.FinCases

open FP4

-- ═══════════════════════════════════════════════════════════════════
-- Concrete alphabet: 3 symbols encoded as Bool × Bool
-- We use Fin 3 as our alphabet: 0=a, 1=b, 2=H
-- ═══════════════════════════════════════════════════════════════════

/-- Helper: encode a Fin 3 symbol as 2 bits -/
def encode3 : Fin 3 → List Bool
  | ⟨0, _⟩ => [false, false]
  | ⟨1, _⟩ => [false, true]
  | ⟨2, _⟩ => [true, true]

/-- Helper: decode 2 bits to Fin 3 -/
def decode3 : List Bool → Option (Fin 3)
  | [false, false] => some ⟨0, by omega⟩
  | [false, true]  => some ⟨1, by omega⟩
  | [true, true]   => some ⟨2, by omega⟩
  | _ => none

/-- Encoding for Fin 3 with blockSize=2 -/
def enc3 : TagEncoding (Fin 3) where
  blockSize := 2
  blockSize_pos := by omega
  encode := encode3
  encode_length := by
    intro a; fin_cases a <;> decide
  encode_injective := by
    intro a b heq
    fin_cases a <;> fin_cases b <;> simp_all [encode3]
  decode := decode3
  decode_encode := by
    intro a; fin_cases a <;> decide

-- Shorthand
def a : Fin 3 := ⟨0, by omega⟩
def b : Fin 3 := ⟨1, by omega⟩
def H : Fin 3 := ⟨2, by omega⟩

-- ═══════════════════════════════════════════════════════════════════
-- Machine 2: {a→[b,H], b→[a], H→[]}  init=[a,a,a]
-- This is the main cross-check machine (Machine 1 halts immediately,
-- Machine 3 doesn't halt — Machine 2 is the best test).
-- ═══════════════════════════════════════════════════════════════════

/-- Tag system: a→[b,H], b→[a], H→[] -/
def ts2 : TagSystem (Fin 3) where
  isHalt := fun x => x = H
  isHalt_dec := fun x => inferInstanceAs (Decidable (x = H))
  production := fun
    | ⟨0, _⟩ => [b, H]     -- a → bH
    | ⟨1, _⟩ => [a]        -- b → a
    | ⟨2, _⟩ => []         -- H → ε

-- ═══════════════════════════════════════════════════════════════════
-- CROSS-CHECK 1: tagStep traces
-- Run tagStep on [a,a,a] and print each configuration.
-- Python trace says: [a,a,a] → [a,b,H] → [H,a] → halt
-- ═══════════════════════════════════════════════════════════════════

#eval do
  IO.println "=== CROSS-CHECK 1: tagStep trace for Machine 2 ==="
  IO.println s!"Initial config: {([a,a,a] : List (Fin 3))}"

  -- Step 0→1: tagStep [a,a,a]
  let step1 := tagStep ts2 [a, a, a]
  IO.println s!"Step 0→1: tagStep [a,a,a] = {step1}"

  -- Step 1→2: tagStep [a,b,H]
  match step1 with
  | some c1 =>
    IO.println s!"  config after step 1: {c1}"
    let step2 := tagStep ts2 c1
    IO.println s!"Step 1→2: tagStep {c1} = {step2}"
    match step2 with
    | some c2 =>
      IO.println s!"  config after step 2: {c2}"
      let step3 := tagStep ts2 c2
      IO.println s!"Step 2→3: tagStep {c2} = {step3}"
      IO.println s!"  (should be none — halt on H)"
    | none => IO.println "  HALTED at step 2"
  | none => IO.println "  HALTED at step 1"

-- ═══════════════════════════════════════════════════════════════════
-- CROSS-CHECK 2: encodeConfig / decodeConfig round-trip
-- Verify: decodeConfig(encodeConfig([a,a,a])) = some [a,a,a]
-- ═══════════════════════════════════════════════════════════════════

#eval do
  IO.println ""
  IO.println "=== CROSS-CHECK 2: encodeConfig/decodeConfig round-trip ==="

  let config0 : TagConfig (Fin 3) := [a, a, a]
  let encoded := encodeConfig enc3 config0
  IO.println s!"encodeConfig [a,a,a] = {encoded}"
  IO.println s!"  (expect: [false,false,false,false,false,false] = 000000)"

  let decoded := decodeConfig enc3 encoded
  IO.println s!"decodeConfig {encoded} = {decoded}"
  IO.println s!"  (expect: some [0,0,0])"

  -- Check round-trip
  match decoded with
  | some d =>
    if d == config0 then
      IO.println "  ROUND-TRIP: PASS"
    else
      IO.println s!"  ROUND-TRIP: FAIL — got {d}, expected {config0}"
  | none =>
    IO.println "  ROUND-TRIP: FAIL — decode returned none"

-- ═══════════════════════════════════════════════════════════════════
-- CROSS-CHECK 3: encodeConfig at each step of the trace
-- ═══════════════════════════════════════════════════════════════════

#eval do
  IO.println ""
  IO.println "=== CROSS-CHECK 3: encodeConfig at each trace step ==="

  -- Step 0: [a,a,a]
  let c0 : TagConfig (Fin 3) := [a, a, a]
  let e0 := encodeConfig enc3 c0
  IO.println s!"Step 0: config={c0}, encoded={e0}"

  -- Step 1: [a,b,H]
  let c1 : TagConfig (Fin 3) := [a, b, H]
  let e1 := encodeConfig enc3 c1
  IO.println s!"Step 1: config={c1}, encoded={e1}"

  -- Step 2: [H,b,H]
  let c2 : TagConfig (Fin 3) := [H, b, H]
  let e2 := encodeConfig enc3 c2
  IO.println s!"Step 2: config={c2}, encoded={e2}"

  -- Verify decoding at each step
  for (label, bits) in [("Step 0", e0), ("Step 1", e1), ("Step 2", e2)] do
    let dec := decodeConfig enc3 bits
    IO.println s!"  decode({label}): {dec}"

-- ═══════════════════════════════════════════════════════════════════
-- CROSS-CHECK 4: tagRun agrees with step-by-step trace
-- ═══════════════════════════════════════════════════════════════════

#eval do
  IO.println ""
  IO.println "=== CROSS-CHECK 4: tagRun verification ==="

  let c0 : TagConfig (Fin 3) := [a, a, a]

  for i in List.range 5 do
    let ci := tagRun ts2 c0 i
    let si := tagStep ts2 ci
    IO.println s!"tagRun ts2 [a,a,a] {i} = {ci}, tagStep = {si}"

-- ═══════════════════════════════════════════════════════════════════
-- CROSS-CHECK 5: Production table (manually constructed)
-- productionTable is noncomputable, so we build it by hand:
-- For each symbol s in {a,b,H}: encode(s) ++ encodeConfig(production(s))
-- ═══════════════════════════════════════════════════════════════════

#eval do
  IO.println ""
  IO.println "=== CROSS-CHECK 5: Manual production table ==="

  -- a: encode(a) ++ encodeConfig([b,H]) = [0,0] ++ [0,1,1,1] = [0,0,0,1,1,1]
  let prod_a := enc3.encode a ++ encodeConfig enc3 (ts2.production a)
  IO.println s!"Production for a: encode(a)={enc3.encode a}, prod(a)={ts2.production a}"
  IO.println s!"  encoded: {prod_a}"

  -- b: encode(b) ++ encodeConfig([a]) = [0,1] ++ [0,0] = [0,1,0,0]
  let prod_b := enc3.encode b ++ encodeConfig enc3 (ts2.production b)
  IO.println s!"Production for b: encode(b)={enc3.encode b}, prod(b)={ts2.production b}"
  IO.println s!"  encoded: {prod_b}"

  -- H: encode(H) ++ encodeConfig([]) = [1,1] ++ [] = [1,1]
  let prod_H := enc3.encode H ++ encodeConfig enc3 (ts2.production H)
  IO.println s!"Production for H: encode(H)={enc3.encode H}, prod(H)={ts2.production H}"
  IO.println s!"  encoded: {prod_H}"

  -- Full table = prod_a ++ prod_b ++ prod_H
  let table := prod_a ++ prod_b ++ prod_H
  IO.println s!"Full production table: {table}"
  IO.println s!"  length: {table.length}"

  -- Full genome = table ++ encodeConfig(initial config)
  let init_encoded := encodeConfig enc3 [a, a, a]
  let full_genome := table ++ init_encoded
  IO.println s!"Full genome (table ++ encoded [a,a,a]): {full_genome}"
  IO.println s!"  length: {full_genome.length}"
  IO.println ""
  IO.println "Compare these values against V2_WITNESS_TRACE_MACHINE_2.md"
  IO.println "Any disagreement is SEV-1."
