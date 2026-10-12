#!/usr/bin/env python3
"""Run the 3D-FPIM NVSim simulator (SNU-HPCS/3D-FPIM, MICRO'22) with sourced geometry.

The upstream repo ships `tech_params/example.cfg` with every geometry value set
to FIXME (never released).  This script fills it from
data/sources/nand_geometry_for_3dfpim.csv (sourced literature values; see the
`source` column), runs `Calculate.py`, then runs NVSim for

  1. the shipped non-PIM validation configs (3D_NAND_128G/256G/512G.cfg) --
     NVSim prints its own error vs the configured reference read latency;
  2. the shipped PIM config 3D_FPIM.cfg (130x256 subarray, 64 stacks, 5-bit input);
  3. K3 study configs: the arXiv 2511.12860 plane (256 rows x 2048 BLs x 128 stacks)
     with InputPrecision 1/2/4/8 (time-encoded input bits per pass), and variants.

Usage: python scripts/sims/run_fpim.py [--fpim /home/user/ext/3D-FPIM/3DFPIM-NVSim]
Writes data/sim_outputs/fpim/*.log and fpim_results.json
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.environ.get("K3_FPIM_OUT", os.path.join(ROOT, "data", "sim_outputs", "fpim"))
GEOM_CSV = os.environ.get("K3_GEOM_CSV", os.path.join(ROOT, "data", "sources", "nand_geometry_for_3dfpim.csv"))

TECH_TEMPLATE = """[temperature]
TEMP = {TEMP}
[staircase]
STAIR_LENGTH = {STAIR_LENGTH}
NUM_STAIRS = {NUM_STAIRS}
TRENCH_WIDTH = {TRENCH_WIDTH}
[wordline]
Barrier_width = {Barrier_width}
L_g = {L_g}
L_g_tr = {L_g_tr}
L_spacer = L_g - Barrier_width * 2
[channel]
r_f = {r_f}
t_si = {t_si}
r = r_f + t_si
t_1 = {t_1}
t_2 = {t_2}
t_3 = {t_3}
t_4 = {t_4}
t_ox = t_1 + t_2 + t_3 + t_4
W_f = {W_f}
H_f = {H_f}
W_g = W_f - (r + t_ox)
H_g = H_f - (r + t_ox)
[material]
epsilon_sio = 4.2 * permittivity
epsilon_si = 11.7 * permittivity
epsilon_sion = 5.3 * permittivity
epsilon_sin = 7.5 * permittivity
epsilon_alo = 5.7 * permittivity
Tungsten_Resistivity = 5e-7 * (1 + 0.0045 * (TEMP - 293))
Polysi_Resistivity = 1./3. * 1e-3
"""


def load_geometry():
    g = {}
    for r in csv.DictReader(open(GEOM_CSV)):
        g[r["param"].strip()] = r["value_m"].strip()
    need = ["STAIR_LENGTH", "NUM_STAIRS", "TRENCH_WIDTH", "Barrier_width", "L_g", "L_g_tr", "r_f", "t_si",
            "t_1", "t_2", "t_3", "t_4", "W_f", "H_f"]
    missing = [k for k in need if k not in g or g[k] in ("", "unknown", "None")]
    if missing:
        raise SystemExit(f"geometry missing: {missing}")
    return g


def write_cfg(path, rows, cols, stacks, pim, inprec=5, mux=2, cap=64e-15, lp=1, cell="3D_FPIM.cell", ref=None, bits=None):
    lines = ["-ProcessNode: 22", f"-PIMMode: {pim}"]
    if pim:
        lines += [f"-LPDecoder: {lp}"]
    lines += [f"-FlashNumStack: {stacks}", f"-MuxSenseAmp: {mux}", f"-ForceSubarray (Total AxB): {rows}x{cols}",
              "-DeviceRoadmap: LSTP", f"-MemoryCellInputFile: {cell}"]
    if pim:
        lines += [f"-InputPrecision: {inprec}", f"-capLoad: {cap}"]
    else:
        lines += [f"-ReferenceReadLatency: {ref}", f"-BitsPerCell: {bits}"]
    open(path, "w").write("\n".join(lines) + "\n")


def parse(text):
    out = {}
    pats = {
        "error_pct": r"\|--- Error = ([0-9.eE+-]+)",
        "subarray_latency_ns": r"SubArray Latency = ([0-9.eE+-]+) ns",
        "decoding_latency_ns": r"Decoding Latency = ([0-9.eE+-]+) ns",
        "senseamp_latency_ns": r"Senseamp Latency = ([0-9.eE+-]+) ns",
        "precharge_latency_ns": r"\|--- Precharge Latency = ([0-9.eE+-]+) ns",
        "rowdec_NR_ns": r"Row Decoder Latency \(NR\) = ([0-9.eE+-]+) ns",
        "rowdec_SR_ns": r"Row Decoder Latency \(SR\) = ([0-9.eE+-]+) ns",
        "rowdec_CR_ns": r"Row Decoder Latency \(CR\) = ([0-9.eE+-]+) ns",
        "cap_drive_ns": r"Capacitor Drive Latency = ([0-9.eE+-]+) ns",
        # NOTE: upstream prints these with a "fJ" label but multiplies joules by 1e12 (= pJ)
        "cell_plus_others_pJ": r"CELL \+ Others = ([0-9.eE+-]+) fJ",
        "load_cap_pJ": r"Load Capacitor = ([0-9.eE+-]+) fJ",
        "rowdec_energy_SR_pJ": r"Row Decoder Energy \(SR\) = ([0-9.eE+-]+) fJ",
        "rowdec_energy_NR_pJ": r"Row Decoder Energy \(NR\) = ([0-9.eE+-]+) fJ",
        "rowdec_energy_CR_pJ": r"Row Decoder Energy \(CR\) = ([0-9.eE+-]+) fJ",
        "leakage_nW": r"Leakage = ([0-9.eE+-]+) nW",
        "area_mm2": r"Total Area = ([0-9.eE+-]+)",
    }
    for k, p in pats.items():
        m = re.search(p, text)
        if m:
            out[k] = float(m.group(1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fpim", default="/home/user/ext/3D-FPIM/3DFPIM-NVSim")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    g = load_geometry()
    sim = a.fpim
    subprocess.run(["make", "-s"], cwd=sim, check=True, capture_output=True)
    results = {"geometry": g}
    runs = []
    # (name, temp, cfg-writer-args)
    runs.append(("val_128G", 360, None, "3D_NAND_128G.cfg"))
    runs.append(("val_256G", 360, None, "3D_NAND_256G.cfg"))
    runs.append(("val_512G", 360, None, "3D_NAND_512G.cfg"))
    runs.append(("fpim_default_130x256x64_p5", 300, None, "3D_FPIM.cfg"))
    for p in (1, 2, 4, 8):
        runs.append((f"k3_arxiv_plane_256x2048x128_p{p}", 300,
                     dict(rows=256, cols=2048, stacks=128, pim=1, inprec=p, mux=4), None))
    for rows, cols, stacks in ((128, 1024, 64), (256, 1024, 128), (512, 2048, 128), (256, 4096, 128), (256, 2048, 64)):
        runs.append((f"k3_plane_{rows}x{cols}x{stacks}_p1", 300,
                     dict(rows=rows, cols=cols, stacks=stacks, pim=1, inprec=1, mux=4), None))
    for name, temp, kw, shipped in runs:
        gg = dict(g)
        gg["TEMP"] = temp
        tp = os.path.join(sim, "tech_params")
        open(os.path.join(tp, "k3.cfg"), "w").write(TECH_TEMPLATE.format(**gg))
        subprocess.run(["python3", "Calculate.py", "k3.cfg"], cwd=tp, check=True, capture_output=True)
        cfg = shipped
        if kw:
            cfg = f"k3_{name}.cfg"
            write_cfg(os.path.join(sim, cfg), **kw)
        r = subprocess.run(["./3DNAND_SIM", cfg], cwd=sim, capture_output=True, text=True)
        txt = r.stdout + r.stderr
        open(os.path.join(OUT, f"{name}.log"), "w").write(txt)
        res = parse(txt)
        res["cfg"] = cfg
        res["temp_K"] = temp
        if kw:
            res.update(kw)
        results[name] = res
        print(name, res, flush=True)
    for f in ("stringWire.cfg", "contactWire.cfg", "wordlineWire.cfg", "selectlineWire.cfg", "parasitic.cfg",
              "cellDimension.cfg"):
        src = os.path.join(sim, "tech_params", "config", f)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(OUT, "derived_" + f))
    json.dump(results, open(os.path.join(OUT, "fpim_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
