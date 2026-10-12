"""Capacity, silicon-area and manufacturing-cost model.

Rules (from the study brief): no transistor-area-to-dollar conversion without
a manufacturing basis; unsupported costs are reported as `unknown`.

Manufacturing basis used (all from data/sources/cost_parameters_sourced.csv):
  * NAND-process silicon $/mm2 = market-implied value of a 300 mm 1Tb-TLC wafer
    (N25a/N25b: $59.0k shortage Sep-2026, $8.24k normalised Jun-2025) divided by
    its gross die area (N22a x N17 = 1522 x 43.54 mm2).  Cross-check: Gartner
    5-7 c/GB manufacturing cost (N28) at ~15 Gb/mm2 -> $0.09-0.13/mm2.
    A custom NAND-PIM die is assumed to cost the same per mm2 as commodity
    NAND *once in volume* (assumption); engineering lots are `unknown` (N30).
  * Logic $/mm2 = TSMC wafer price (L02-L06) / 66,000 mm2 usable area.
  * Die yield: Poisson with defect density D0 (assumption, recorded).
  * Packaging, assembly, test, board, power delivery: `unknown` (N31) except
    where a finished-product price brackets them (SSD teardown N14-N16).
"""
from __future__ import annotations

import math

from .scheduler import adc_area_m2

WAFER_GROSS_MM2 = 1522 * 43.54                       # N22a x N17
NAND_WAFER_VALUE = {"normalized": 8240.11, "shortage": 59041.42}   # N25b, N25a
LOGIC_WAFER = {"N28": 3000.0, "N16": 5500.0, "N7": 9500.0, "N5": 18500.0, "N3": 20000.0}  # L06,L05,L04,L03,L02
LOGIC_USABLE_MM2 = 66000.0
DRAM_USD_PER_GB = {"normalized": 3.0, "shortage": 19.5}   # D02 DDR5 pre-shortage; D08 LPDDR5X 2026
HBM_USD_PER_GB = {"normalized": 12.0, "shortage": 15.0}   # D09, D12

# Peripheral areas (per plane) from arXiv 2511.12860 Table II (7nm-scaled LV peri):
HV_PERI_MM2 = 0.004210
LV_PERI_NONADC_MM2 = 0.0030     # Table II LV-peri 0.00451 incl. ADC; non-ADC share assumed ~2/3
RPU_HTREE_MM2 = 0.000077


def nand_usd_per_mm2(price):
    return NAND_WAFER_VALUE[price] / WAFER_GROSS_MM2


def logic_usd_per_mm2(node):
    return LOGIC_WAFER[node] / LOGIC_USABLE_MM2


def poisson_yield(area_mm2, d0_per_cm2):
    return math.exp(-area_mm2 / 100.0 * d0_per_cm2)


def analog_nand_area(arch):
    """Return per-die and total areas for an analog NAND-PIM (or FeNAND) design."""
    planes = arch["planes"]
    cells_per_plane = arch["array_rows"] * arch["array_cols"] * arch["array_stacks"]
    cell_density = arch["density_gb_mm2"] * 1e9 / 4.0           # cells/mm2 (density quoted for QLC)
    plane_array_mm2 = cells_per_plane / cell_density
    pooled = arch.get("adc_sharing") == "die_pool"
    adc_mm2 = 0.0 if pooled else arch["adcs_per_array"] * adc_area_m2(arch["adc_bits"], arch) * 1e6
    cap_mm2 = arch["array_cols"] / 2 * arch.get("int_cap_area_m2", 8e-12) * 1e6   # integration/sample cap per BL pair
    plane_cmos_mm2 = HV_PERI_MM2 + LV_PERI_NONADC_MM2 + RPU_HTREE_MM2 + adc_mm2 + cap_mm2
    if arch.get("silicon") == "modified_periphery":
        plane_cmos_mm2 = plane_array_mm2 * 0.25 + adc_mm2        # commodity CuA periphery + added ADCs
    plane_mm2 = max(plane_array_mm2, plane_cmos_mm2)            # CMOS under array
    ppd = arch["planes_per_die"]
    pool_mm2 = arch["adc_pool_per_die"] * adc_area_m2(arch["adc_bits"], arch) * 1e6 if pooled else 0.0
    die_mm2 = ppd * plane_mm2 + pool_mm2 + 2.0                   # + die controller / IO / pumps (assumption)
    dies = math.ceil(planes / ppd)
    adc_total = dies * arch["adc_pool_per_die"] if pooled else planes * arch["adcs_per_array"]
    return dict(dies=dies, die_mm2=die_mm2, total_mm2=dies * die_mm2, plane_array_mm2=plane_array_mm2,
                plane_cmos_mm2=plane_cmos_mm2, adc_mm2_per_plane=adc_mm2, adc_pool_mm2_per_die=pool_mm2,
                adc_total=adc_total, cmos_over_array=(plane_cmos_mm2 * ppd + pool_mm2) / (plane_array_mm2 * ppd),
                silicon_process="NAND (CuA)")


def digital_nand_area(arch):
    if arch["variant"] in ("A0", "A1"):
        die_mm2 = 43.54 if arch["variant"] == "A0" else (43.54 if arch["scenario"] != "opt" else 60.0)
        add = 0.0 if arch["variant"] == "A0" else arch["planes_per_die"] * 0.5   # per-plane MAC + logic
        return dict(dies=arch["dies"], die_mm2=die_mm2 + add, total_mm2=arch["dies"] * (die_mm2 + add),
                    sa_count=arch["sa_count"], silicon_process="NAND")
    # A2: many small SLC planes; CMOS = SAs/page buffers + MAC logic
    planes = arch["planes_total"]
    cols = arch["page_bytes"] * 8
    sa_mm2 = cols * arch["sa_area_m2"] * 1e6
    mac_mm2 = 0.002 * (arch["plane_mac_rate"] / 2e9)
    cells_per_plane = 256 * cols * 128
    plane_array_mm2 = cells_per_plane / (arch.get("cell_density_g_mm2", 3.21) * 1e9)
    plane_mm2 = max(plane_array_mm2, sa_mm2 + mac_mm2 + HV_PERI_MM2)
    die_mm2 = arch["planes_per_die"] * plane_mm2 + 2.0
    return dict(dies=arch["dies"], die_mm2=die_mm2, total_mm2=arch["dies"] * die_mm2, sa_count=planes * cols,
                plane_array_mm2=plane_array_mm2, plane_cmos_mm2=sa_mm2 + mac_mm2 + HV_PERI_MM2,
                silicon_process="NAND (CuA)")


def rram_area(arch):
    cells = arch["cells_total"]
    arr_mm2 = cells / arch["cells_per_mm2"]          # NeuroSim density already includes per-array ADCs/periphery
    adc_mm2 = 0.0
    if arch.get("adc_sharing") == "die_pool":
        adc_mm2 = arch["dies_total"] * arch["adc_pool_per_die"] * adc_area_m2(arch["adc_bits"], arch) * 1e6
    total = arr_mm2 + adc_mm2
    die = 100.0
    return dict(dies=math.ceil(total / die), die_mm2=die, total_mm2=total, array_mm2=arr_mm2, adc_mm2=adc_mm2,
                silicon_process="logic 22-28nm + BEOL RRAM")


HBM_STACK = dict(bw=1.2e12, gb=36.0)            # HBM3E 12-high: ~1.2 TB/s, 36 GB (gpu_systems / cost sources)
LPDDR_CH = dict(bw=68e9, gb=2.0)                # LPDDR5X-8533 x64 channel, >=2 GB per channel
SRAM_MBIT_PER_MM2 = 31.8 * 1.048576             # TSMC N3E HD macro 31.8 Mib/mm2 (D15 derivation in cost sources)
LOGIC_MM2_PER_TFLOP = 0.5                       # assumption anchored to B200: ~2.25 PF BF16 in ~1,600 mm2 incl. I/O


def orchestrator_cost(arch, context, price):
    """Bottom-up cost of the attention/orchestrator engine + its memory.

    logic die(s) at N5 sized by sustained FLOP/s, on-die SRAM for the KDA state when it is held on-chip,
    and DRAM sized by BOTH bandwidth and capacity (HBM stacks or LPDDR channels are indivisible).
    Packaging (2.5D interposer for HBM) is unknown (N31) and not included.
    """
    flops = arch["attn_flops"]
    kv_gb = arch.get("kv_bytes", 2.0) * 576 * 24 * context / 1e9
    kda_gb = 0.449
    sram_mm2 = 0.0
    if "SRAM" in str(arch.get("kda_in", "")):
        sram_mm2 = kda_gb * 8e3 / SRAM_MBIT_PER_MM2
    else:
        kv_gb += kda_gb
    if arch.get("kv_in_sram"):
        # KV cache held on-die: SRAM area sized to the context, no external DRAM
        sram_mm2 += kv_gb * 8e3 / SRAM_MBIT_PER_MM2
    logic_mm2 = 40.0 + flops / 1e12 * LOGIC_MM2_PER_TFLOP * arch.get("attn_area_factor", 1.0) + sram_mm2
    n_dies = max(1, math.ceil(logic_mm2 / 800.0))
    die_mm2 = logic_mm2 / n_dies
    logic_usd = n_dies * die_mm2 * logic_usd_per_mm2("N5") / poisson_yield(die_mm2, 0.1)
    bw = arch["kv_bw_Bps"]
    if arch.get("kv_in_sram"):
        return logic_usd, {"attention_engine_mm2": logic_mm2, "attention_engine_dies": n_dies,
                           "attention_engine_usd": logic_usd, "kv_state_GB": kv_gb,
                           "kv_mem": f"on-die SRAM {sram_mm2:.0f} mm2", "kv_mem_usd": 0.0}
    opts = []
    stacks = max(math.ceil(bw / HBM_STACK["bw"]), math.ceil(kv_gb / HBM_STACK["gb"]), 1)
    opts.append((stacks * HBM_STACK["gb"] * HBM_USD_PER_GB[price], f"{stacks} HBM3E stacks ({stacks * HBM_STACK['gb']:.0f} GB)"))
    ch = max(math.ceil(bw / LPDDR_CH["bw"]), 1)
    if ch <= 32:                                   # beyond ~32 x64 channels the pin count is impractical
        gb = max(kv_gb, ch * LPDDR_CH["gb"])
        opts.append((gb * DRAM_USD_PER_GB[price], f"{ch} LPDDR5X channels ({gb:.0f} GB)"))
    mem_usd, mem_desc = min(opts)
    return logic_usd + mem_usd, {"attention_engine_mm2": logic_mm2, "attention_engine_dies": n_dies,
                                 "attention_engine_usd": logic_usd, "kv_state_GB": kv_gb, "kv_mem": mem_desc,
                                 "kv_mem_usd": mem_usd}


def cost_estimate(arch, context=131072, price="normalized", d0=0.1):
    """Volume silicon cost (USD) with explicit unknowns."""
    fam = arch["family"]
    out = {"price_scenario": price, "unknown_items": "packaging/assembly/test (N31); board/power delivery; NRE"}
    if fam == "gpu":
        out.update(silicon_usd=None, system_market_usd=550000.0 if "GB300" in arch["name"] else 320000.0,
                   basis="market price: 8 GPUs of GB300 NVL72 (~$5M/72) or DGX B200 8x$30-40k")
        return out
    if fam == "analog_cim" and arch["tech"] in ("nand3d", "fenand3d"):
        a = analog_nand_area(arch)
        usd_mm2 = nand_usd_per_mm2(price)
    elif fam == "analog_cim":
        a = rram_area(arch)
        usd_mm2 = logic_usd_per_mm2("N28")
    else:
        a = digital_nand_area(arch)
        usd_mm2 = nand_usd_per_mm2(price)
    y = poisson_yield(a["die_mm2"], d0)
    mem_usd = a["total_mm2"] * usd_mm2 / y
    orch_usd, od = orchestrator_cost(arch, context, price)
    out.update(a)
    out.update(od)
    out.update(usd_per_mm2=usd_mm2, die_yield=y, memory_silicon_usd=mem_usd,
               orchestrator_and_kv_usd=orch_usd,
               silicon_usd=(mem_usd + orch_usd) if orch_usd is not None else None)
    return out


# ----------------------------------------------------------------------------- first prototype
EUR_USD = 1.08   # assumption for converting Europractice EUR prices
PROTO_ITEMS = {
    "mpw_28nm_min_block_usd": 10609 * EUR_USD,      # M07 Europractice TSMC 28nm HPC+, 1 mm2 minimum (standard)
    "mpw_16nm_min_block_usd": 30592 * EUR_USD,      # M08
    "mpw_22fdx_per_mm2_usd": 17820 * EUR_USD,       # M10 GF 22FDX, min 4 mm2
    "mask_set_28nm_usd": 1.0e6,                     # M01
    "mask_set_5nm_usd": 6.5e6,                      # M05
}


def prototype_cost(arch):
    """First experimental prototype: what is known vs unknown (USD)."""
    fam, sil = arch["family"], arch.get("silicon")
    out = {"prototype_known_usd": 0.0, "prototype_unknown": [], "prototype_items": []}

    def add(name, usd):
        out["prototype_items"].append(f"{name}: {usd:,.0f}")
        out["prototype_known_usd"] += usd

    if fam == "gpu":
        add("8-GPU system (market)", arch.get("system_price_usd", 325000.0))
        return out
    if sil == "commodity":
        add("1.6 TB enterprise QLC SSD capacity (C05 floor)", 187.2)
        out["prototype_unknown"].append("host accelerator (any GPU/CPU; not the bottleneck)")
        return out
    # logic test chip for the orchestrator / ADC pool / periphery: 4 mm2 at 28nm MPW
    add("28nm MPW test chip, 4 mm2 (ADC pool + near-array logic)", 4 * PROTO_ITEMS["mpw_28nm_min_block_usd"])
    if arch.get("tech") in ("nand3d", "fenand3d", "nand3d_digital"):
        out["prototype_unknown"].append("custom 3D-NAND array engineering lot (N30: no public price; requires a NAND fab partner)")
        if arch.get("tech") == "fenand3d":
            out["prototype_unknown"].append("ferroelectric 3D NAND process (research-stage; no foundry offering)")
    if arch.get("tech") == "rram3d":
        out["prototype_unknown"].append("TSMC 22/28nm RRAM MPW option price (M11 unknown); vertical RRAM has no foundry offering")
    out["prototype_unknown"].append("packaging/assembly/test (N31), board, firmware/NRE engineering")
    return out
