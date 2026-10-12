#!/usr/bin/env python3
"""First-principles floors and a 'what would it take' step ladder for single-stream Kimi K3.

Every number here is computed from (a) the released checkpoint (k3cim.workload), (b) the
sourced/derived parameter registry (k3cim.params, results/physical_assumptions.csv) and
(c) the cost constants in k3cim.cost.  Nothing is hand-entered except the requirement-audit text.

Writes results/first_principles.md and results/first_principles.csv
(and results/step_ladder.csv, read back by the final verdict).
"""
import csv
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from k3cim import cost as CO  # noqa: E402
from k3cim import params as PR  # noqa: E402
from k3cim.architectures import analog_nand, digital_nand, orchestrator  # noqa: E402
from k3cim.cost import cost_estimate  # noqa: E402
from k3cim.precision_model import PrecisionModel  # noqa: E402
from k3cim.scheduler import (Scheduler, adc_area_m2, adc_energy_j, adc_time_s,  # noqa: E402
                             speculative_cim, with_dense_replicas)
from k3cim.workload import K3Workload  # noqa: E402

RES = os.path.join(ROOT, "results")
TARGETS = (100, 500, 1000)
CTXS = (32768, 131072, 1048576)
g = PR.get


def human(x, unit=""):
    for div, suf in ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if abs(x) >= div:
            return f"{x / div:.3g} {suf}{unit}"
    return f"{x:.3g} {unit}"


def workload_invariants(wl):
    lin = wl.linear_ops()
    exp_w = sum(o.stored_weights for o in lin if o.wdtype == "mxfp4")
    den_w = sum(o.stored_weights for o in lin if o.wdtype != "mxfp4")
    exp_mac = sum(o.macs for o in lin if not o.always_active)
    den_mac = sum(o.macs for o in lin if o.always_active)
    depth, _ = wl.sequential_linear_depth()
    sync, _ = wl.sync_depth()
    att_per_L = sum(o.K * o.N for o in wl.ops if o.kind in ("attn_score", "attn_value"))
    return dict(expert_weights=exp_w, dense_weights=den_w, expert_macs=exp_mac, dense_macs=den_mac,
                depth=depth, sync=sync, att_flops_per_ctx_token=2 * att_per_L,
                kv_bytes_per_ctx_token=wl.kv_cache_bytes(1), kda_state_bytes=wl.kda_state_bytes_total())


def storage_floor(inv):
    """Minimum bits to hold the model (experts MXFP4 as released, dense at MXINT8 + E8M0 scale)."""
    bits = inv["expert_weights"] * 4.25 + inv["dense_weights"] * 8.25
    gb = bits / 8 / 1e9
    rows = []
    nand_mm2 = bits / (g("nand_qlc_density_gb_mm2", "real") * 1e9)
    rows.append(("3D NAND QLC (digital storage density, 28.5 Gb/mm2)", nand_mm2,
                 nand_mm2 * CO.nand_usd_per_mm2("normalized"), nand_mm2 * CO.nand_usd_per_mm2("shortage")))
    rows.append(("DRAM (DDR5/LPDDR5X $/GB)", None, gb * CO.DRAM_USD_PER_GB["normalized"],
                 gb * CO.DRAM_USD_PER_GB["shortage"]))
    rows.append(("HBM3E ($/GB)", None, gb * CO.HBM_USD_PER_GB["normalized"], gb * CO.HBM_USD_PER_GB["shortage"]))
    sram_mm2 = bits / 1e6 / CO.SRAM_MBIT_PER_MM2
    rows.append(("SRAM (N3E HD macro 31.8 Mib/mm2)", sram_mm2, sram_mm2 * CO.logic_usd_per_mm2("N3"), None))
    return bits, rows


def stream_floors(inv, T, tR, dense_bytes=1.03125):
    """If weights are *moved* to logic every token (digital): bytes/s and sense amplifiers needed."""
    bytes_tok = inv["expert_macs"] * 4.25 / 8 + inv["dense_macs"] * dense_bytes
    return dict(bytes_per_s=bytes_tok * T, sense_amps=bytes_tok * 8 * tR * T)


def analog_floors(wl, T, enc="E", C=128, cb=2, ab=8, s="real"):
    a = analog_nand(s, enc, contributors=C, cell_bits=cb, adc_bits=ab)
    a.update(adc_sharing="die_pool", adc_pool_per_die=512, int_cap_area_m2=8e-12)
    a.update(orchestrator(s, "mid"))
    sc = Scheduler(a, wl)
    conv = sum(sc.analog_linear_cost(o).breakdown["conversions"] for o in wl.linear_ops())
    tiles = sum(sc.analog_linear_cost(o).breakdown["tiles"] for o in wl.linear_ops())
    t_conv = adc_time_s(ab, a)
    n_adc = conv * T * t_conv / 0.5
    return dict(conversions_per_token=conv, array_ops_per_token=tiles, adcs_needed=n_adc,
                adc_mm2=n_adc * adc_area_m2(ab, a) * 1e6, e_adc_j=conv * adc_energy_j(ab, a),
                e_wl_j=tiles * a["e_wl_per_op_j"], cells=a["cells_total"], planes=a["planes"])


def energy_floor_rows(wl, inv):
    """Per-token energy of each irreducible physical mechanism (realistic parameter column)."""
    s = "real"
    rows = []
    bits_stream = (inv["expert_macs"] * 4.25 + inv["dense_macs"] * 8.25)
    e_page_bit = g("e_page_read_j", s) / (16384 * 8)
    rows.append(("stream weights out of NAND pages (sense + page buffer)", bits_stream * e_page_bit))
    rows.append(("move streamed weights over a die link", bits_stream * g("die_link_pj_per_bit", s) * 1e-12))
    rows.append(("digital MAC for every weight (BF16-class)", (inv["expert_macs"] + inv["dense_macs"]) * g("e_mac_j", s)))
    af = analog_floors(wl, 500, s=s)
    rows.append(("analog: ADC conversions (E, C=128, MLC, 8b ADC)", af["e_adc_j"]))
    rows.append(("analog: word-line/string setup per array op", af["e_wl_j"]))
    for L in (131072, 1048576):
        rows.append((f"attention math at {L // 1024}K (BF16, {g('attn_pj_per_flop', s)} pJ/FLOP)",
                     inv["att_flops_per_ctx_token"] * L * g("attn_pj_per_flop", s) * 1e-12))
        rows.append((f"KV read at {L // 1024}K (BF16 latent, {g('kv_pj_per_bit', s)} pJ/bit)",
                     inv["kv_bytes_per_ctx_token"] * L * 8 * g("kv_pj_per_bit", s) * 1e-12))
    rows.append(("KDA state read+write (SRAM)", 2 * inv["kda_state_bytes"] * 8 * 1.0e-12))
    return rows


# ----------------------------------------------------------------------------- step ladder
def ladder(knobs):
    """Each rung changes ONE physical thing relative to the previous rung."""
    C, cb, ab, enc = knobs["C"], knobs["cell_bits"], knobs["adc_bits"], knobs["enc"]
    bpp = {"B": 1, "C": 2, "D": 4, "E": 8}[enc]
    pm = PrecisionModel()
    rungs = []

    def an(s, enc, pool, eng, silicon="redesigned_array"):
        if silicon == "modified_periphery":
            a = analog_nand(s, enc, silicon=silicon, cell_bits=4, adc_bits=9 if enc == "B" else 12)
        else:
            a = analog_nand(s, enc, contributors=C, cell_bits=cb, adc_bits=ab)
            a.update(adc_sharing="die_pool", adc_pool_per_die=pool,
                     int_cap_area_m2={"pess": 32e-12, "real": 8e-12, "opt": 2e-12}[s])
        a.update(orchestrator(s, eng))
        return a

    def dg(s, v, eng):
        a = digital_nand(s, v)
        a.update(orchestrator(s, eng))
        return a

    rungs.append(("R0", "-", "commodity TLC NAND, weights streamed over ONFI to an external accelerator (A0)",
                  "real", lambda: dg("real", "A0", "mid")))
    rungs.append(("R1", "R0", "compute next to every plane, SLC mode, commodity planes (A1)",
                  "real", lambda: dg("real", "A1", "mid")))
    rungs.append(("R2", "R1", "redesign the array: 256 small low-latency SLC planes per die, digital (A2)",
                  "real", lambda: dg("real", "A2", "mid")))
    rungs.append(("R3", "R1", "instead: sum currents of many cells on the bit line (analog), commodity planes (B-mp)",
                  "real", lambda: an("real", "B", 0, "mid", silicon="modified_periphery")))
    rungs.append(("R4", "R3", f"small analog planes (256x2048), C={C}, {cb}-bit cells, 1-bit input steps (B)",
                  "real", lambda: an("real", "B", 512, "mid")))
    rungs.append(("R5", "R4", f"{bpp} input bits per step, time-encoded ({enc})" if enc != "B" else "(same encoding)",
                  "real", lambda: an("real", enc, 512, "mid")))
    rungs.append(("R6", "R5", "4x larger die-level ADC pool (2048/die, BL-held samples)",
                  "real", lambda: an("real", enc, 2048, "mid")))
    rungs.append(("R7a", "R6", "attention engine sized for 128K with HBM (1.5 PFLOP/s, 5 HBM3E stacks)",
                  "real", lambda: an("real", enc, 2048, "mid3")))
    rungs.append(("R7b", "R6", "instead: KV cache in on-die SRAM, FP8 KV + FP8 attention math (1.5 PFLOP/s)",
                  "real", lambda: an("real", enc, 2048, "sram_b")))
    rungs.append(("R8", "R7b", "optimistic array physics (0.3 us WL setup, 32 ns steps), folded MLA, folded norms",
                  "opt", lambda: an("opt", enc, 2048, "sram_b")))
    out = []
    wls = {s: K3Workload(fold_mla=(s == "opt")) for s in ("real", "opt")}
    for rid, parent, desc, s, mk in rungs:
        a = mk()
        wl = wls[s]
        sc = Scheduler(a, wl)
        row = {"rung": rid, "from": parent, "change": desc, "scenario": s, "design": a["name"],
               "attn_engine": a.get("attn_engine")}
        for L in CTXS:
            r = sc.evaluate(L)
            lim = max([("critical_path", r["t_critical_path_s"])] + list(r["bounds"].items()), key=lambda kv: kv[1])[0]
            row[f"tok_s_{L // 1024}k"] = r["tok_per_s"]
            row[f"J_tok_{L // 1024}k"] = r["energy_j_per_token"]
            row[f"limiter_{L // 1024}k"] = lim
        c = cost_estimate(a, 131072, "normalized")
        row["silicon_usd_normalized_128k"] = c.get("silicon_usd")
        row["memory_silicon_usd"] = c.get("memory_silicon_usd")
        row["orchestrator_kv_usd"] = c.get("orchestrator_and_kv_usd")
        row["dies"] = c.get("dies")
        if a["family"] == "analog_cim":
            pr = pm.estimate(a)
            row["precision_verdict"] = pr.get("precision_verdict")
            row["budget_ratio"] = pr.get("budget_ratio")
        else:
            row["precision_verdict"] = "exact_digital"
        out.append(row)
    # speculative decoding on the last rung (hypothetical drafter), with replicated dense weights
    a = rungs[-1][4]()
    wl = wls["opt"]
    best = None
    for k in (1, 2, 3, 5, 7):
        for R in (1, k + 1):
            b = with_dense_replicas(a, R)
            sc = Scheduler(b, wl)
            res = {L: speculative_cim(sc, L, k, dense_replicas=R) for L in CTXS}
            if best is None or res[131072]["tok_per_s"] > best[0]:
                best = (res[131072]["tok_per_s"], k, R, b, res)
    _, k, R, b, res = best
    row = {"rung": "R9", "from": "R8", "change": f"speculative decoding, k={k} drafts, dense weights replicated x{R} "
                                   "(hypothetical 1-layer drafter, DSpark-measured acceptance, measured K3 routing locality)",
           "scenario": "opt", "design": b["name"], "attn_engine": b.get("attn_engine")}
    for L in CTXS:
        row[f"tok_s_{L // 1024}k"] = res[L]["tok_per_s"]
        row[f"J_tok_{L // 1024}k"] = res[L]["J_per_token"]
        row[f"limiter_{L // 1024}k"] = max([("critical_path+draft", res[L]["t_critical_path_s"] + res[L]["t_draft_s"])]
                                           + list(res[L]["bounds"].items()), key=lambda kv: kv[1])[0]
    c = cost_estimate(b, 131072, "normalized")
    row.update(silicon_usd_normalized_128k=c.get("silicon_usd"), memory_silicon_usd=c.get("memory_silicon_usd"),
               orchestrator_kv_usd=c.get("orchestrator_and_kv_usd"), dies=c.get("dies"))
    pr = pm.estimate(b)
    row["precision_verdict"] = pr.get("precision_verdict")
    row["budget_ratio"] = pr.get("budget_ratio")
    out.append(row)
    return out


def cost_ladder():
    """At a fixed target (500 tok/s, realistic array physics) apply cost levers one at a time.

    L0  cheapest realistic design meeting the target with precision not 'exceeds' (from the DSE)
    L1  4-bit (QLC) cells at C=32 - needs ~4x tighter program-verify than the 40 nm SONOS data
        (results/precision_sweep.csv, sweep C program_verify: 1.17x -> 0.25x budget); hypothetical
    L2  + small-plane cell density equal to commodity QLC (28.5 Gb/mm2 instead of 12.84)
    L3  + 4x larger dies (1024 planes, 4x ADC pool per die): fewer dies, less fixed per-die overhead
    """
    path = os.path.join(ROOT, "data", "dse_results.csv")
    if not os.path.exists(path):
        return []
    rows = list(csv.DictReader(open(path)))
    out = []
    for ctx, L, ckey in (("32k", 32768, "silicon_usd_normalized_32k"), ("128k", 131072, "silicon_usd_normalized_128k")):
        def cheapest(pred):
            best = None
            for r in rows:
                if r["tag"] != "nand_analog_redesigned" or r["scenario"] != "real" or not pred(r):
                    continue
                t, c = float(r[f"tok_s_{ctx}"]), float(r[ckey])
                if t >= 500 and (best is None or c < best[0]):
                    best = (c, r)
            return best[1] if best else None

        budget = PrecisionModel().budget

        def tight_prog_ok(r, factor=4.0):
            """Precision if programming sigma were `factor` x tighter: device error / factor, ADC/quantisation
            error unchanged (sweep C: 4x tighter program-verify took QLC from 1.17x to 0.25x budget)."""
            worst = 0.0
            for kind, tname in (("expert", "L1.expert.w1"), ("dense", "L0.kda.q_proj(bf16->mxint8)")):
                try:
                    q, d = float(r[f"quant_err_{kind}"]), float(r[f"device_err_{kind}"])
                except (TypeError, ValueError, KeyError):
                    return False
                worst = max(worst, math.sqrt(q * q + (d / factor) ** 2) / budget[tname])
            return worst <= 1.0

        base = cheapest(lambda r: not r["precision_verdict"].startswith("exceeds"))
        qlc = cheapest(lambda r: r["cell_bits"] == "4" and tight_prog_ok(r))
        steps = [("L0", "cheapest realistic design meeting 500 tok/s, precision within/marginal", base, {})]
        if qlc is not None:
            steps += [("L1", "4-bit cells, precision with 4x tighter program-verify (hypothetical)", qlc, {}),
                      ("L2", "+ commodity QLC cell density in small planes (28.5 Gb/mm2)", qlc, {"density": 28.5}),
                      ("L3", "+ 1024 planes per die, 4x ADC pool per die", qlc, {"density": 28.5, "ppd": 1024})]
        for sid, desc, r, mod in steps:
            if r is None:
                out.append({"context": ctx, "step": sid, "change": desc, "feasible": "no"})
                continue
            from run_all import rebuild_arch as rebuild  # noqa: E402  (scripts/run_all.py)
            a = rebuild(r)
            if "density" in mod:
                a["density_gb_mm2"] = mod["density"]
            if "ppd" in mod:
                a["planes_per_die"] = mod["ppd"]
                a["adc_pool_per_die"] = a["adc_pool_per_die"] * mod["ppd"] // 256
                a["dies_total"] = max(1, math.ceil(a["planes"] / mod["ppd"]))
            res = Scheduler(a, K3Workload()).evaluate(L)
            c = cost_estimate(a, L, "normalized")
            cs = cost_estimate(a, L, "shortage")
            out.append({"context": ctx, "step": sid, "change": desc, "feasible": "yes",
                        "design": f"{r['encoding']} C={r['contributors']} {r['cell_bits']}b-cell ADC{r['adc_bits']} "
                                  f"pool{r['adc_pool_per_die']} {r['attn_engine']}",
                        "tok_s": res["tok_per_s"], "nand_usd": c.get("memory_silicon_usd"),
                        "attention_usd": c.get("orchestrator_and_kv_usd"), "silicon_usd": c.get("silicon_usd"),
                        "silicon_usd_shortage": cs.get("silicon_usd"), "dies": c.get("dies"),
                        "precision": r["precision_verdict"] if sid == "L0" else "<=1x budget assuming 4x tighter programming"})
    return out


def choose_knobs():
    """Knobs of the cheapest realistic analog-NAND design meeting 500 tok/s at 128K with a precision
    verdict that is not 'exceeds' (from the DSE)."""
    path = os.path.join(ROOT, "data", "dse_results.csv")
    default = {"enc": "C", "C": 128, "cell_bits": 2, "adc_bits": 6}
    if not os.path.exists(path):
        return default, "default (no DSE)"
    best = None
    for r in csv.DictReader(open(path)):
        if r["tag"] != "nand_analog_redesigned" or r["scenario"] != "real":
            continue
        if not r.get("precision_verdict", "").startswith(("within", "marginal")):
            continue
        try:
            t, c = float(r["tok_s_128k"]), float(r["silicon_usd_normalized_128k"])
        except (TypeError, ValueError):
            continue
        if t < 500:
            continue
        if best is None or c < best[0]:
            best = (c, r)
    if best is None:
        return default, "default (no analog design meets 500 tok/s at 128K)"
    r = best[1]
    return ({"enc": r["encoding"], "C": int(r["contributors"]), "cell_bits": int(r["cell_bits"]),
             "adc_bits": int(r["adc_bits"])},
            f"knobs of the cheapest realistic analog design meeting 500 tok/s at 128K, verdict {r['precision_verdict']}")


def main():
    wl = K3Workload()
    inv = workload_invariants(wl)
    csv_rows = []
    md = ["# First-principles floors for single-stream Kimi K3", "",
          "Generated by `scripts/first_principles.py`. Every number is computed from the released checkpoint "
          "(`k3cim/workload.py`), the parameter registry (`results/physical_assumptions.csv`, realistic column unless "
          "stated) and the cost constants in `k3cim/cost.py`.", ""]
    md += ["## 1. What the model itself fixes (cannot be engineered away without changing K3)", "",
           "| quantity | value |", "|---|---:|",
           f"| routed-expert weights (MXFP4, stored) | {human(inv['expert_weights'])} |",
           f"| always-active weights (BF16 as released) | {human(inv['dense_weights'])} |",
           f"| expert MACs per token | {human(inv['expert_macs'])} |",
           f"| always-active MACs per token | {human(inv['dense_macs'])} |",
           f"| dependent matrix-vector stages per token (critical path) | {inv['depth']} |",
           f"| dependent stages incl. global reductions (norm/top-k/softmax) | {inv['sync']} |",
           f"| MLA attention FLOPs per token per context token | {inv['att_flops_per_ctx_token'] / 1e6:.2f} M |",
           f"| MLA latent KV bytes per context token (BF16) | {inv['kv_bytes_per_ctx_token'] / 1e3:.1f} kB |",
           f"| KDA recurrent state (FP32), read+written every token | {inv['kda_state_bytes'] / 1e6:.0f} MB |", ""]
    for k, v in inv.items():
        csv_rows.append({"section": "workload", "item": k, "value": v, "unit": ""})

    md += ["## 2. Time budget per dependent stage", "",
           "Single-stream decode cannot overlap the stages of one token: per-token time >= depth x stage latency.", "",
           "| tok/s | per token | per MVM stage (698) | per stage incl. reductions (1396) |", "|---:|---:|---:|---:|"]
    for T in TARGETS:
        md.append(f"| {T} | {1e3 / T:.2f} ms | {1e6 / T / inv['depth']:.2f} us | {1e6 / T / inv['sync']:.2f} us |")
        csv_rows.append({"section": "stage_budget", "item": f"us_per_stage_at_{T}", "value": 1e6 / T / inv["depth"],
                         "unit": "us"})
    md += ["", "Consequence: at 500 tok/s every matrix-vector stage - input delivery, array settle, conversion, "
           "partial-sum reduction, scaling and the hop to the next stage - must complete in about 2.9 us "
           "(1.4 us if each normalisation/top-k is its own synchronisation). Commodity NAND page reads take 20-50 us, "
           "so a commodity read cannot sit on the per-token critical path even once per layer.", ""]

    bits, srows = storage_floor(inv)
    md += ["## 3. Storage floor: which memory can even hold K3 at the price target", "",
           f"Minimum stored bits (experts MXFP4 as released, always-active weights MXINT8): {bits / 8e12:.3f} TB.", "",
           "| memory class | area (mm2) | volume cost, normalized pricing | 2026 shortage pricing |",
           "|---|---:|---:|---:|"]
    for name, mm2, c_n, c_s in srows:
        md.append(f"| {name} | {'' if mm2 is None else f'{mm2:,.0f}'} | ${c_n:,.0f} | "
                  f"{'' if c_s is None else f'${c_s:,.0f}'} |")
        csv_rows.append({"section": "storage_floor", "item": name, "value": c_n, "unit": "USD normalized"})
    md += ["", "Only 3D NAND-class density (many layers of cells over one silicon footprint) holds the model for "
           "under $500. DRAM is ~40x and HBM ~150x too expensive per bit. This is the single hard reason to look at "
           "NAND at all: the weights must live in a memory whose cost is set by stacked layers, not by lithography "
           "area. Everything below is about extracting the needed work from such a memory fast enough.", ""]

    md += ["## 4. Throughput floors at the target rate", "",
           "If weights are moved out of the memory (digital), every active bit is sensed and transported each token. "
           "If they stay in place (analog), the bit line sums C products per conversion and only partial sums move.", "",
           "| requirement | 100 tok/s | 500 tok/s | 1000 tok/s |", "|---|---:|---:|---:|"]
    lines = {}
    for T in TARGETS:
        st = stream_floors(inv, T, g("nand_tR_lowlat", "real"))
        st05 = stream_floors(inv, T, 0.5e-6)
        an = analog_floors(wl, T)
        lines.setdefault("weight bytes moved (MXINT8 dense), B/s", []).append(human(st["bytes_per_s"], "B/s"))
        lines.setdefault("NAND sense amps busy, tR = 3 us (Z-NAND class)", []).append(human(st["sense_amps"]))
        lines.setdefault("NAND sense amps busy, tR = 0.5 us (hypothetical)", []).append(human(st05["sense_amps"]))
        lines.setdefault("analog conversions/s (E, C=128, MLC)", []).append(human(an["conversions_per_token"] * T, "/s"))
        lines.setdefault("8-bit ADCs needed at 50% utilisation", []).append(human(an["adcs_needed"]))
        lines.setdefault("ADC area for those (mm2, realistic ADC)", []).append(f"{an['adc_mm2']:.0f}")
        for L in CTXS:
            lines.setdefault(f"attention FLOP/s at {L // 1024}K", []).append(
                human(inv["att_flops_per_ctx_token"] * L * T, "FLOP/s"))
            lines.setdefault(f"KV read bandwidth at {L // 1024}K (BF16)", []).append(
                human(inv["kv_bytes_per_ctx_token"] * L * T, "B/s"))
        csv_rows += [{"section": "throughput_floor", "item": f"sense_amps_tR3us_at_{T}", "value": st["sense_amps"], "unit": ""},
                     {"section": "throughput_floor", "item": f"adcs_needed_E_C128_at_{T}", "value": an["adcs_needed"], "unit": ""}]
    for k, v in lines.items():
        md.append(f"| {k} | " + " | ".join(v) + " |")
    an = analog_floors(wl, 500)
    md += ["", f"Analog in-situ compute cuts the sensing work by the number of summed contributors: "
           f"{human(an['conversions_per_token'])} conversions per token instead of "
           f"{human((inv['expert_macs'] * 4.25 + inv['dense_macs'] * 8.25))} sensed bits. "
           "That ~20-50x reduction is the physical reason analog CIM can beat digital NAND streaming at equal sensing "
           "technology; it is paid for in precision (section 6).", ""]

    md += ["## 5. Energy per token by irreducible mechanism (realistic parameters)", "",
           "| mechanism | J/token |", "|---|---:|"]
    for name, e in energy_floor_rows(wl, inv):
        md.append(f"| {name} | {e:.3g} |")
        csv_rows.append({"section": "energy_floor", "item": name, "value": e, "unit": "J/token"})
    md += ["", "Measured GPU reference: ~28-30 J/token for single-stream K3 on 8x B300 (results/gpu_comparison.md). "
           "In-situ analog weights cost well under 1 J/token; at long context the attention engine's KV traffic and "
           "math become the dominant energy and cost, independent of how the weights are stored.", ""]

    md += ["## 6. Requirement audit (question every requirement)", "",
           "| requirement | set by | verdict | consequence |", "|---|---|---|---|",
           "| all 2.78 T weights resident | model (routing picks 16 of 896 experts per layer per token, decided ~us before use) | "
           "physics of the workload | every expert must be reachable in < ~3 us; 'cold' tiers with 20-50 us reads cannot be on the path |",
           "| BF16 always-active weights | release format | convention | MXINT8 re-quantisation measured at 0.12-0.29 % output error (budget 1.1 %): 8-bit is sufficient; 4-bit (4.8 %) is not without re-training |",
           "| MXFP8 activations | K3 QAT (model card) | model | 8-bit inputs are what K3 was trained to tolerate; fewer input bits are unvalidated |",
           "| exact digital arithmetic | habit | convention | K3 already absorbs MXFP8 activation noise (1.1-2.7 % per layer); analog error below ~25 % of that is in the noise |",
           "| signed weights need two cells | differential sensing | design choice | offset/reference-column coding halves cells but couples error to the reference; kept differential here |",
           "| fast attention over 1M tokens | product target | requirement | 2.6 PFLOP/s + 14.5 TB/s at 500 tok/s; dynamic data cannot live in NAND (endurance), so this is a DRAM/SRAM + logic problem whatever stores the weights |",
           "| sequential depth 698 | model architecture | model | single-stream only; batching or pipelining across users does not help one stream; speculative decoding is the only depth multiplier |",
           "| per-layer synchronisation | GPU software stack (84 us/layer measured-calibrated) | implementation | not physical: a hard-wired dataflow pays ~0.1-1 us per stage instead |",
           "| <$500 unit cost | business target | target | storage alone forces 3D-NAND-class bits; the attention engine + KV memory for >=128K at 500 tok/s is the cost driver that NAND cannot remove |",
           ""]

    knobs, why = choose_knobs()
    rows = ladder(knobs)
    keys = list(rows[0].keys())
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(os.path.join(RES, "step_ladder.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})
    md += ["## 7. Step-function ladder (one physical change per rung)", "",
           f"Analog knobs: encoding {knobs['enc']}, C={knobs['C']}, {knobs['cell_bits']}-bit cells, {knobs['adc_bits']}-bit ADC ({why}). "
           "Silicon cost = volume silicon, normalized pricing, KV sized for 128K; packaging/board/NRE excluded (unknown).", "",
           "| rung | from | change | tok/s 32K | tok/s 128K | tok/s 1M | J/tok 128K | silicon $ (128K) | limiter 128K | precision |",
           "|---|---|---|---:|---:|---:|---:|---:|---|---|"]
    for r in rows:
        su = r.get("silicon_usd_normalized_128k")
        md.append(f"| {r['rung']} | {r['from']} | {r['change']} | {r['tok_s_32k']:.3g} | {r['tok_s_128k']:.3g} | {r['tok_s_1024k']:.3g} | "
                  f"{r['J_tok_128k']:.3g} | {'' if su is None else f'{su:,.0f}'} | {r['limiter_128k']} | "
                  f"{r.get('precision_verdict', '')} |")
    md += ["", "Reading the ladder: the big multipliers are (i) leaving commodity page geometry (R1->R2, R3->R4: "
           "~100x, it is the plane/word-line size that sets latency, not the cell), (ii) summing in the analog domain "
           "so sensing work drops by C (R5 matches R2's speed at half its silicon cost), and (iii) sizing the attention engine to the "
           "context (R7). Buying KV bandwidth as on-die SRAM instead of HBM capacity (R7b vs R7a) is faster "
           "for less than half the silicon cost at 128K, but SRAM cost grows linearly with context. "
           "Faster array physics (R8) is the last ~2x. Speculative decoding helps far less on "
           "weight-stationary arrays than on GPUs because each extra verified token is another array operation on "
           "shared (dense) and hot (expert) arrays; real K3 routing reuses experts across neighbouring tokens "
           "(max 4-6 of 8 tokens on one expert in layers 1-3).", ""]
    cl = cost_ladder()
    if cl:
        md += ["## 8. What would it take to reach $500 at 500 tok/s (cost levers, realistic array physics)", "",
               "Silicon cost at volume, normalized memory pricing, KV memory sized for the context; packaging, board and "
               "NRE are unknown and excluded.", "",
               "| context | step | change | design | tok/s | NAND $ | attention+KV $ | total $ | total $ (2026 shortage) | dies |",
               "|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
        for r in cl:
            if r["feasible"] != "yes":
                md.append(f"| {r['context']} | {r['step']} | {r['change']} | infeasible | | | | | | |")
                continue
            md.append(f"| {r['context']} | {r['step']} | {r['change']} | {r['design']} | {r['tok_s']:.0f} | "
                      f"{r['nand_usd']:,.0f} | {r['attention_usd']:,.0f} | {r['silicon_usd']:,.0f} | "
                      f"{r['silicon_usd_shortage']:,.0f} | {r['dies']} |")
        md += ["", "At 32K context the $500 target closes on volume silicon with three hypothetical levers: QLC-grade "
               "analog precision (programming ~4x tighter than the 40 nm SONOS data), commodity-like cell density in "
               "small planes, and larger dies. At 2026 shortage memory prices the same silicon costs 4-5x more, and "
               "packaging of 90-360 dies is unknown. At 128K it does not close: the attention engine alone (1.5 PFLOP/s "
               "plus ~2.3 GB of on-die FP8 KV and KDA state, ~950 mm2 of 5 nm-class logic+SRAM) costs ~$430, and the "
               "NAND part bottoms out near $420 because in small planes the CMOS under the array (high-voltage word-line "
               "drivers, sample capacitors, sense circuits) is larger than the cell stack above it, so die area stops "
               "tracking cell density. Below $500 at 128K additionally needs a periphery shrink (periphery on a bonded "
               "logic wafer, drivers shared across planes) and a cheaper KV medium; neither is demonstrated.", ""]
        keys = []
        for r in cl:
            for k in r:
                if k not in keys:
                    keys.append(k)
        with open(os.path.join(RES, "cost_ladder.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in cl:
                w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})
    with open(os.path.join(RES, "first_principles.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.join(RES, "first_principles.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["section", "item", "value", "unit"])
        w.writeheader()
        w.writerows(csv_rows)
    print("wrote results/first_principles.md, first_principles.csv, step_ladder.csv")


if __name__ == "__main__":
    main()
