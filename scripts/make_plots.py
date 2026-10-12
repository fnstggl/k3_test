#!/usr/bin/env python3
"""Plots for the K3 CIM study (results/plots/*.png).

Palette: reference categorical slots (blue, orange, aqua) in fixed order for at most
three colour groups, plus neutral ink for the GPU reference; identity is always also
carried by direct labels or marker shape.  One y-axis per chart.
"""
import csv
import json
import math
import os
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLOTS = os.path.join(ROOT, "results", "plots")
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

GROUP = {  # architecture tag -> (group label, colour, marker)
    "digital_nand_A0": ("digital NAND", S1, "s"), "digital_nand_A1": ("digital NAND", S1, "s"),
    "digital_nand_A2": ("digital NAND", S1, "s"),
    "nand_analog_redesigned": ("analog 3D NAND", S2, "o"), "nand_analog_modified_periphery": ("analog 3D NAND", S2, "o"),
    "fenand_speculative": ("other analog NVM", S3, "^"), "rram_3d": ("other analog NVM", S3, "^"),
    "gpu": ("GPU (measured-calibrated)", INK, "D"),
}
LABEL = {"digital_nand_A0": "A0", "digital_nand_A1": "A1", "digital_nand_A2": "A2", "rram_3d": "F 3D RRAM",
         "fenand_speculative": "G FeNAND", "gpu": "H 8xB300", "nand_analog_modified_periphery": "B/E on commodity planes"}


def style(ax, title, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=10)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.tick_params(colors=INK2, labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.6, zorder=0)


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(path):
    return list(csv.DictReader(open(path))) if os.path.exists(path) else []


def pareto(points):
    pts = sorted(points, key=lambda p: (p[0], -p[1]))
    out, best = [], -1
    for c, t, r in pts:
        if t > best:
            out.append((c, t, r))
            best = t
    return out


def plot_cost_vs_speed(dse, scen="real", ctx="128k"):
    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    style(ax, f"Single-stream K3 decode vs volume silicon cost — {ctx} context, '{scen}' scenario",
          "silicon cost, USD (normalized 2025 memory prices; GPU = market price)", "tokens / s (one user)")
    by = defaultdict(list)
    for r in dse:
        if r["scenario"] != scen:
            continue
        c = f(r["silicon_usd_normalized_128k"]) or f(r.get("system_market_usd"))
        t = f(r[f"tok_s_{ctx}"])
        if c and t and not r.get("precision_verdict", "").startswith("exceeds"):
            by[r["tag"]].append((c, t, r))
    seen = set()
    for tag, pts in by.items():
        g, col, mk = GROUP[tag]
        fr = pareto(pts)
        xs, ys = [p[0] for p in fr], [p[1] for p in fr]
        lab = g if g not in seen else None
        seen.add(g)
        ax.plot(xs, ys, marker=mk, markersize=6, linewidth=1.6, color=col, label=lab,
                markeredgecolor=SURFACE, markeredgewidth=1.0, zorder=3)
        name = LABEL.get(tag, tag.replace("nand_analog_redesigned", "B-E redesigned NAND"))
        ax.annotate(name, (xs[-1], ys[-1]), textcoords="offset points", xytext=(6, 2), fontsize=7.5, color=INK2)
    for y, lab in ((100, "100"), (500, "500 target"), (1000, "1000")):
        ax.axhline(y, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)), zorder=1)
        ax.text(ax.get_xlim()[0] if False else 12, y * 1.04, lab + " tok/s", fontsize=7, color=MUTED)
    ax.axvline(500, color=MUTED, linewidth=0.8, linestyle=(0, (1, 2)))
    ax.text(520, 0.6, "$500", fontsize=7, color=MUTED)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(10, 2e6)
    ax.set_ylim(0.1, 5000)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.text(0.0, -0.16, "Pareto fronts of the design-space exploration; points whose analog error exceeds the MXFP8 budget are excluded. "
            "Packaging/board/NRE costs are unknown and not included.", transform=ax.transAxes, fontsize=7, color=MUTED)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, f"tokens_vs_cost_{scen}_{ctx}.png"), dpi=150)
    plt.close(fig)


def plot_tok_vs_context(comp):
    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    style(ax, "Best design per architecture: tokens/s vs context ('real' scenario, fastest config)",
          "context length (tokens)", "tokens / s (one user)")
    rows = [r for r in comp if r["scenario"] == "real" and r["selection"] == "fastest_at_128K" and r.get("feasible") == "yes"]
    xs = [32768, 131072, 1048576]
    order = ["H", "A2", "E", "B", "F", "G", "A1", "A0"]
    rows.sort(key=lambda r: order.index(r["arch_id"]) if r["arch_id"] in order else 99)
    cols = {"H": INK, "A2": S1, "A1": S1, "A0": S1, "E": S2, "B": S2, "C": S2, "D": S2, "B-mp": S2, "E-mp": S2, "F": S3, "G": S3}
    mks = {"H": "D", "A0": "s", "A1": "s", "A2": "s", "F": "^", "G": "^"}
    for r in rows:
        ys = [f(r["tok_s_32k"]), f(r["tok_s_128k"]), f(r["tok_s_1024k"])]
        if None in ys:
            continue
        ax.plot(xs, ys, color=cols.get(r["arch_id"], MUTED), marker=mks.get(r["arch_id"], "o"), linewidth=1.6,
                markersize=6, markeredgecolor=SURFACE)
        ax.annotate(r["arch_id"], (xs[-1], ys[-1]), textcoords="offset points", xytext=(6, -2), fontsize=8, color=INK2)
    ax.axhline(500, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
    ax.text(33000, 530, "500 tok/s target", fontsize=7, color=MUTED)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(xs)
    ax.set_xticklabels(["32K", "128K", "1M"])
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "tokens_vs_context.png"), dpi=150)
    plt.close(fig)


def plot_energy(energy):
    rows = [r for r in energy if r["scenario"] == "real" and r["context"] == "131072" and r["design"] == "fastest_at_128K"]
    if not rows:
        return
    rows.sort(key=lambda r: f(r["J_per_token"]))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    style(ax, "Energy per generated token at 128K context ('real' scenario, fastest design)", "", "joules / token (log)")
    xs = np.arange(len(rows))
    ax.bar(xs, [f(r["J_per_token"]) for r in rows], color=S1, width=0.6, zorder=3)
    for i, r in enumerate(rows):
        ax.text(i, f(r["J_per_token"]) * 1.1, f"{f(r['J_per_token']):.2g} J\n{f(r['W']):.0f} W", ha="center", fontsize=7, color=INK2)
    ax.set_xticks(xs)
    ax.set_xticklabels([r["arch_id"] for r in rows], fontsize=8)
    ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "energy_per_token.png"), dpi=150)
    plt.close(fig)


def plot_capacity(cost):
    rows = [r for r in cost if r["scenario"] == "real" and r["price_scenario"] == "normalized" and r["kv_context"] == "131072"
            and r["design"] == "cheapest_meeting_100tok_s_at_128K" and f(r.get("total_mm2"))]
    if not rows:
        return
    seen, uniq = set(), []
    for r in rows:
        if r["arch_id"] not in seen:
            seen.add(r["arch_id"])
            uniq.append(r)
    uniq.sort(key=lambda r: f(r["total_mm2"]))
    fig, ax = plt.subplots(figsize=(8, 4.2))
    style(ax, "Silicon needed to hold all 2.78T K3 parameters (cheapest design meeting 100 tok/s @128K, 'real')",
          "", "memory-die silicon area, mm² (log)")
    xs = np.arange(len(uniq))
    ax.bar(xs, [f(r["total_mm2"]) for r in uniq], color=S2, width=0.6, zorder=3)
    for i, r in enumerate(uniq):
        ax.text(i, f(r["total_mm2"]) * 1.12, f"{int(float(r['dies']))} dies\n{f(r['effective_bits_per_weight']):.1f} b/w",
                ha="center", fontsize=7, color=INK2)
    ax.axhline(1522 * 43.54 / 1522 * 12.5, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
    ax.text(-0.4, 1522 * 43.54 / 1522 * 12.5 * 1.08, "12.5 commodity 1Tb TLC dies (1.56 TB as plain storage)", fontsize=7, color=MUTED)
    ax.set_xticks(xs)
    ax.set_xticklabels([r["arch_id"] for r in uniq], fontsize=8)
    ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "capacity_area.png"), dpi=150)
    plt.close(fig)


def plot_precision(sweep):
    rows = [r for r in sweep if r["sweep"] == "A_ideal_device" and r["tensor"] == "L1.expert.w1"]
    if not rows:
        return
    for bpp in ("1", "8"):
        Cs = [8, 16, 32, 64, 128, 256]
        adcs = list(range(4, 15))
        M = np.full((len(Cs), len(adcs)), np.nan)
        for r in rows:
            if r["cell_bits"] == "4" and r["bits_per_pass"] == bpp:
                i, j = Cs.index(int(r["contributors"])), adcs.index(int(r["adc_bits"]))
                M[i, j] = float(r["budget_ratio"])
        fig, ax = plt.subplots(figsize=(7.5, 4.0))
        style(ax, f"Analog error / MXFP8 budget — real K3 expert, QLC cells, {bpp}-bit input steps, ideal device",
              "ADC resolution (bits)", "contributors per conversion")
        ax.grid(False)
        levels = [0, 0.1, 0.25, 0.5, 1, 2, 4, 1e9]
        cmap = matplotlib.colors.ListedColormap(SEQ)
        norm = matplotlib.colors.BoundaryNorm(levels, cmap.N)
        im = ax.imshow(M, aspect="auto", cmap=cmap, norm=norm, origin="lower")
        ax.set_xticks(range(len(adcs)))
        ax.set_xticklabels(adcs)
        ax.set_yticks(range(len(Cs)))
        ax.set_yticklabels(Cs)
        for i in range(len(Cs)):
            for j in range(len(adcs)):
                if not np.isnan(M[i, j]):
                    v = M[i, j]
                    ax.text(j, i, f"{v:.2g}" if v < 100 else ">99", ha="center", va="center", fontsize=6.5,
                            color=INK if v < 1 else SURFACE)
        cb = fig.colorbar(im, ax=ax, ticks=levels[:-1])
        cb.ax.tick_params(labelsize=7, colors=INK2)
        cb.set_label("error ÷ MXFP8 activation error (≤0.25 safe, >1 exceeds)", fontsize=7, color=INK2)
        fig.tight_layout()
        fig.savefig(os.path.join(PLOTS, f"precision_heatmap_QLC_{bpp}bit_steps.png"), dpi=150)
        plt.close(fig)
    # device comparison
    dev = [r for r in sweep if r["sweep"] == "B_device" and r["tensor"] == "L1.expert.w1" and r["calibration"] == "none"
           and r["contributors"] == "32" and r["bits_per_pass"] == "1"]
    if dev:
        best = {}
        for r in dev:
            k = (r["device_case"], int(r["cell_bits"]))
            v = float(r["budget_ratio"])
            best[k] = min(best.get(k, 1e9), v)
        cases = sorted({k[0] for k in best}, key=lambda c: best.get((c, 4), 0))
        fig, ax = plt.subplots(figsize=(8.5, 4.4))
        style(ax, "Device non-idealities on a real K3 expert MVM (32 contributors, 1-bit steps)", "",
              "error ÷ MXFP8 activation error (log)")
        w = 0.2
        for j, (cb, col) in enumerate(((1, SEQ[2]), (2, SEQ[3]), (3, SEQ[4]), (4, SEQ[6]))):
            xs = np.arange(len(cases)) + (j - 1.5) * w
            ax.bar(xs, [best.get((c, cb), np.nan) for c in cases], width=w * 0.9, color=col, label=f"{cb} bit/cell", zorder=3)
        ax.axhline(1, color=S2, linewidth=1.0)
        ax.text(-0.4, 1.08, "= MXFP8 quantization error (budget)", fontsize=7, color=INK2)
        ax.axhline(0.25, color=MUTED, linewidth=0.8, linestyle=(0, (4, 3)))
        ax.set_xticks(np.arange(len(cases)))
        ax.set_xticklabels([c.replace("generic_sigma", "σ=") + ("%" if "sigma" in c else "") for c in cases], fontsize=7, rotation=20)
        ax.set_yscale("log")
        ax.legend(frameon=False, fontsize=7, ncol=4, loc="upper left")
        fig.tight_layout()
        fig.savefig(os.path.join(PLOTS, "precision_devices.png"), dpi=150)
        plt.close(fig)


def plot_latency_breakdown(lat):
    rows = [r for r in lat if r["layer"] == "TOTAL" and r["scenario"] == "real" and r["context"] == "131072"
            and r["design"] == "fastest_at_128K"]
    if not rows:
        return
    cats = ["cp_attn_proj_mvm_us", "cp_moe_expert_mvm_us", "cp_moe_dense_mvm_us", "cp_mla_attention_us",
            "cp_kda_recurrence_us", "cp_norm_residual_us", "cp_routing_us", "cp_other_us", "cp_dense_mlp_mvm_us",
            "cp_lm_head_mvm_us"]
    names = ["attention projections", "routed experts", "MoE dense (shared/latent/router)", "MLA attention",
             "KDA recurrence", "norms + residuals", "routing", "other", "dense MLP", "lm_head"]
    palette = [S1, S2, S3, "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948", MUTED, INK2]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    style(ax, "Where the per-token critical path goes (128K context, 'real', fastest design)", "", "ms per token")
    bottom = np.zeros(len(rows))
    xs = np.arange(len(rows))
    for c, n, col in zip(cats, names, palette):
        v = np.array([(f(r.get(c)) or 0.0) / 1000 for r in rows])
        if v.sum() == 0:
            continue
        ax.bar(xs, v, bottom=bottom, color=col, width=0.6, label=n, edgecolor=SURFACE, linewidth=1.0, zorder=3)
        bottom += v
    ax.set_xticks(xs)
    ax.set_xticklabels([r["arch_id"] for r in rows], fontsize=8)
    ax.legend(frameon=False, fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "latency_breakdown_128k.png"), dpi=150)
    plt.close(fig)


def plot_ladder(ladder):
    """Step-function ladder: each rung is one physical change; arrows follow 'from'."""
    if not ladder:
        return
    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    style(ax, "What would it take: one physical change per step (128K context)",
          "volume silicon cost, USD (normalized prices, packaging excluded)", "tokens / s (one user)")
    pos = {}
    for r in ladder:
        c, t = f(r["silicon_usd_normalized_128k"]), f(r["tok_s_128k"])
        if c is None or t is None:
            continue
        pos[r["rung"]] = (c, t, r)
    for rid, (c, t, r) in pos.items():
        par = r.get("from")
        if par in pos:
            pc, pt, _ = pos[par]
            ax.annotate("", xy=(c, t), xytext=(pc, pt),
                        arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.0, shrinkA=6, shrinkB=6))
    placed = []
    for rid, (c, t, r) in pos.items():
        analog = r["design"].startswith(("B_", "E_", "C_", "D_"))
        col = S2 if analog else S1
        ax.scatter([c], [t], s=46, color=col, edgecolor=SURFACE, linewidth=2, zorder=3,
                   marker="o" if analog else "s")
        # rungs that share a cost (R4/R5/R6, R8/R9) get fixed label offsets so labels never sit on a neighbour
        off = {"R4": (7, -11), "R5": (-26, 2), "R6": (6, 6), "R8": (-24, -10), "R9": (7, 2)}.get(rid, (7, -3))
        ax.annotate(rid, (c, t), textcoords="offset points", xytext=off, fontsize=8, color=INK)
        placed.append((c, t))
    ax.set_xscale("log")
    ax.set_yscale("log")
    from matplotlib.ticker import FuncFormatter, LogLocator
    ax.xaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    ax.xaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v / 1000:.0f}K" if v >= 1000 else f"${v:.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    for y, lab in ((100, "100"), (500, "500 target"), (1000, "1000")):
        ax.axhline(y, color=GRID, lw=1.2, ls="--", zorder=1)
        ax.annotate(lab, (ax.get_xlim()[0], y), textcoords="offset points", xytext=(4, 3), fontsize=7, color=MUTED)
    ax.axvline(500, color=GRID, lw=1.2, ls=":", zorder=1)
    ax.annotate("$500", (500, ax.get_ylim()[0]), textcoords="offset points", xytext=(3, 4), fontsize=7, color=MUTED)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker="s", ls="", color=S1, label="digital NAND"),
                       Line2D([], [], marker="o", ls="", color=S2, label="analog 3D NAND")],
              frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS, "step_ladder_128k.png"), dpi=150)
    plt.close(fig)


def main():
    os.makedirs(PLOTS, exist_ok=True)
    dse = load(os.path.join(ROOT, "data", "dse_results.csv"))
    comp = load(os.path.join(ROOT, "results", "architecture_comparison.csv"))
    if dse:
        for s in ("pess", "real", "opt"):
            plot_cost_vs_speed(dse, s, "128k")
        plot_cost_vs_speed(dse, "real", "32k")
        plot_cost_vs_speed(dse, "real", "1024k")
    if comp:
        plot_tok_vs_context(comp)
    plot_energy(load(os.path.join(ROOT, "results", "energy_breakdown.csv")))
    plot_capacity(load(os.path.join(ROOT, "results", "cost_model.csv")))
    plot_precision(load(os.path.join(ROOT, "results", "precision_sweep.csv")))
    plot_latency_breakdown(load(os.path.join(ROOT, "results", "latency_breakdown.csv")))
    plot_ladder(load(os.path.join(ROOT, "results", "step_ladder.csv")))
    print("plots:", sorted(os.listdir(PLOTS)))


if __name__ == "__main__":
    main()
