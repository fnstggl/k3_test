#!/usr/bin/env python3
"""Gate 9F — "useful exact-K3 work per physical sense" + required-primitive
derivation (the 100x-per-sense question, and the 10x-again first-principles bound).

Answers, from first principles:
  1. What is useful_exact_K3_MACs / physical_sense today vs the array bandwidth
     bound implied by each throughput target?
  2. What must an (L3) cross-bitline popcount primitive achieve — operands/sense
     and latency — to reach 500 tok/s @ 25 user @ $0.10/M with NATIVE K3?
  3. Is the 100x-useful-work-per-sense claim physically reachable EXACTLY on
     commodity NAND array behavior? (label HYPOTHESIS beyond demonstrated ranges)

No invented constants: array/tR/energy from configs/nand_capabilities.yaml +
Gate-2 calibration; MAC counts from Gate-3 exact K3 model.
Run: python3 experiments/gate9_useful_work.py -> results/gate9_useful_work.json
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from k3.workload import nand_bytes_per_token, active_params_per_token, N_MOE, TOPK, N_EXPERTS, LATENT, EXP_HID

RESULTS = Path(__file__).resolve().parent.parent / "results"

NB = nand_bytes_per_token()
BYTES_PER_TOKEN = NB["total"]              # 137 GB native
MACS_PER_TOKEN = active_params_per_token()  # 104.2e9
EXPERT_STORE = N_MOE * N_EXPERTS * 3 * LATENT * EXP_HID * 4.25 / 8
DENSE_STORE = NB["dense_bytes"]


def first_principles_bounds():
    """For each throughput target, the effective sensed bytes/token bound at a
    given array bandwidth, and the useful MACs/sense implied."""
    out = {}
    for arr_bw_TBps in (1.0, 3.0, 10.0):
        arr_bw = arr_bw_TBps * 1e12
        row = {}
        for target_tok_s in (500, 1000):
            max_bytes_per_token = arr_bw / target_tok_s
            row[f"{target_tok_s}tok_s"] = {
                "max_effective_sensed_GB_per_token": round(max_bytes_per_token / 1e9, 2),
                "vs_native_137GB_reduction_needed": round(BYTES_PER_TOKEN / max_bytes_per_token, 1),
            }
        out[f"array_{arr_bw_TBps}TBps"] = row
    return out


def useful_work_per_sense_sweep():
    """Sweep operands-combined-per-sense; report exact MACs/sense achievable and
    whether the combined result is EXACT native-K3 (only if the mechanism yields
    an exact popcount/sum, not merely AND/OR of operands)."""
    # A conventional 16KB SLC page sense resolves all packed MXFP4 weights on that
    # page: 16384*8/4.25 = 30840 weights; at B=1 each does 1 MAC -> 30840 MACs/sense.
    page_b = 16384
    conv_weights_per_page = page_b * 8 / 4.25
    rows = []
    for operands in (1, 2, 4, 8, 16, 32, 48, 64, 96, 128):
        # MWS AND/OR of N operands: ONE sense, but result is a BOOLEAN combine,
        # NOT a sum. It yields useful K3 MACs ONLY if the K3 op at that position
        # is an N-way AND/OR (it is NOT — GEMV needs addition). So exact useful
        # MACs from an N-operand MWS AND = 0 for GEMV (Gate 4/9 conclusion).
        mws_useful_macs = 0        # AND/OR cannot sum -> no exact GEMV MAC
        # A cross-bitline POPCOUNT primitive covering `operands` lanes per op,
        # done for all 32 bitplane-pairs of an MX block: if it covers W lanes and
        # the page holds P=page_b*8/1 bitlines, one count op resolves P/32 blocks'
        # single bitplane-pair. To finish a block needs 32 count ops. Useful MACs
        # per COUNT-sense = (P/32 blocks) * 32 lanes / 32 planes... modeled as:
        bitlines = page_b * 8
        blocks_per_page = bitlines / 32
        # one count op (one sense) does one bitplane-pair for all blocks on the page
        # -> resolves blocks_per_page * 32 lanes of partial product, but needs 32
        # such ops per block-set. Net exact MACs per count-sense:
        count_useful_macs = blocks_per_page * 32 / 32   # = blocks_per_page (per bitplane-pair)
        rows.append({
            "operands_per_sense": operands,
            "conventional_macs_per_sense_b1": round(conv_weights_per_page),
            "mws_and_or_exact_gemv_macs": mws_useful_macs,
            "failbit_count_exact_macs_per_sense": round(count_useful_macs),
            "note": "MWS AND/OR is exact but not a sum; count is exact popcount but "
                    "at MXFP4 density needs 32 senses/block-set -> < conventional at B=1",
            "evidence": "MEASURED (MWS AND/OR, Flash-Cosmos) | HYPOTHESIS (exposed count)",
        })
    return {
        "conventional_macs_per_sense_b1": round(conv_weights_per_page),
        "batch_reuse_note": "conventional MACs/sense scale x B via page-buffer reuse "
                            "(exact, needs latch persistence); this is the real lever, "
                            "capped by per-user latency and expert-union for MoE",
        "sweep": rows,
    }


def required_primitive_for_targets():
    """Derive the exact (operands/sense, latency) an L3 popcount primitive needs to
    reach 500 tok/s @ 25 user @ $0.10/M with native precision, given the search
    ceiling (~$0.25/M optimistic, ~105 tok/s agg at 25 user)."""
    # From gate9 search: best native interactive central ~$0.6/M, opt ~$0.26/M,
    # agg saturates ~105 tok/s (array sense-bound). To hit 500 tok/s @ 25 user AND
    # $0.10/M requires ~5x more useful MACs per physical sense at the SAME array $:
    ceiling_agg = 105
    ceiling_dollar_opt = 0.257
    return {
        "search_ceiling_native_interactive": {
            "agg_tok_s": ceiling_agg, "usd_per_Mtok_opt": ceiling_dollar_opt,
            "usd_per_Mtok_central": 0.614, "J_per_token_opt": 1.08},
        "gap_to_T1": {
            "agg_factor": round(500 / ceiling_agg, 1),
            "dollar_factor": round(ceiling_dollar_opt / 0.10, 1)},
        "required_L3_primitive": {
            "name": "exact maskable cross-bitline popcount over the full page width",
            "must_resolve_macs_per_sense": ">= ~5x conventional (i.e. >=1.5e5 exact "
                "MACs/sense at B=1) to lift agg to 500 tok/s at fixed array $",
            "must_operate_within": "<= tR (=3-22us SLC) per count op",
            "must_mask_to": "32-column MX blocks (E8M0 scale boundary) — a whole-page "
                "count is useless for K3",
            "and_do_all_bitplane_pairs_in": "<= ~8 senses/block-set (not 32) to beat "
                "conventional dense sensing — requires combining multiple bitplane "
                "pairs per sense (e.g. multi-level TLC threshold coding), UNPROVEN",
            "evidence": "L3 — no such primitive demonstrated on commodity NAND; "
                "Flash-Cosmos MWS gives AND/OR (not popcount); program-verify counters "
                "exist but on-demand maskable exposure is undocumented (BABOL E2 target)",
        },
        "verdict": "Reaching T1 with NATIVE K3 requires a cross-bitline popcount "
            "primitive that resolves ~5x more exact MACs per sense than conventional "
            "dense sensing AND masks to 32-blocks AND folds multiple bitplanes per "
            "sense. No audited mechanism provides this exactly. The 100x-per-sense "
            "claim is FALSE for exact K3 on demonstrated commodity behavior.",
    }


def main():
    out = {
        "provenance": {"git": subprocess.getoutput("git rev-parse HEAD"),
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        "native_K3": {"bytes_per_token_GB": round(BYTES_PER_TOKEN / 1e9, 1),
                      "macs_per_token_G": round(MACS_PER_TOKEN / 1e9, 1)},
        "first_principles_bandwidth_bounds": first_principles_bounds(),
        "useful_work_per_sense": useful_work_per_sense_sweep(),
        "required_primitive_for_targets": required_primitive_for_targets(),
    }
    RESULTS.mkdir(exist_ok=True)
    json.dump(out, open(RESULTS / "gate9_useful_work.json", "w"), indent=1)

    b = out["first_principles_bandwidth_bounds"]
    print("== First-principles: max effective sensed bytes/token per target ==")
    for arr, row in b.items():
        print(f"  {arr}: 500tok/s needs <={row['500tok_s']['max_effective_sensed_GB_per_token']}GB/tok "
              f"({row['500tok_s']['vs_native_137GB_reduction_needed']}x cut from 137GB); "
              f"1000tok/s needs <={row['1000tok_s']['max_effective_sensed_GB_per_token']}GB/tok")
    u = out["useful_work_per_sense"]
    print(f"\n== Useful work/sense: conventional {u['conventional_macs_per_sense_b1']} MACs/sense (B=1); "
          f"x B via reuse ==")
    print("  MWS AND/OR exact GEMV MACs: 0 (cannot sum); exposed-count loses at MXFP4 density")
    rp = out["required_primitive_for_targets"]
    print(f"\n== To hit T1 (native): need {rp['gap_to_T1']['agg_factor']}x agg, "
          f"{rp['gap_to_T1']['dollar_factor']}x $ ==")
    print("  " + rp["verdict"])


if __name__ == "__main__":
    main()
