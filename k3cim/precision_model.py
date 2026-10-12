"""Accuracy estimate for an analog architecture point, from the real-tensor studies.

err_total^2 = err_quant^2 (ideal device: weight/input integer rendering + ADC,
              results/precision_sweep.csv sweep A)
            + err_device^2 (device-only, data/sim_outputs/crosssim/device_grid.json)

Budget = MXFP8 activation-quantisation error of the same MVM (what K3's QAT
already tolerates).  Verdict thresholds (assumption, see final_verdict.md):
  ratio <= 0.25 : within budget;  <= 1 : marginal (needs end-to-end eval);  > 1 : exceeds.
"""
from __future__ import annotations

import csv
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWEEP = os.path.join(ROOT, "results", "precision_sweep.csv")
GRID = os.path.join(ROOT, "data", "sim_outputs", "crosssim", "device_grid.json")
TENSORS = {"expert": "L1.expert.w1", "dense": "L0.kda.q_proj(bf16->mxint8)"}
DEVICE_FOR_TECH = {"nand3d": "SONOS_t1d", "fenand3d": "generic_1pct", "rram3d": "RRAMMilo"}


class PrecisionModel:
    def __init__(self, device_override=None):
        self.ok = os.path.exists(SWEEP) and os.path.exists(GRID)
        self.quant, self.budget = {}, {}
        self.dev = {}
        self.device_override = device_override
        if not self.ok:
            return
        rows = [r for r in csv.DictReader(open(SWEEP))
                if r["sweep"] in ("A_ideal_device", "A_ideal_device_calibrated_range")]
        for r in rows:
            if r["sweep"] == "A_ideal_device":
                self.budget[r["tensor"]] = float(r["mxfp8_budget_err"])
        for r in rows:
            key = (r["tensor"], int(r["cell_bits"]), int(r["contributors"]), int(r["bits_per_pass"]), int(r["adc_bits"]))
            # calibrated-range rows are evaluated on held-out tokens: express them on the full-batch budget scale
            err = float(r["budget_ratio"]) * self.budget[r["tensor"]]
            # the design may use either full-scale or calibrated ADC ranging: keep the better one
            self.quant[key] = min(err, self.quant.get(key, err))
        self.dev = json.load(open(GRID))

    def _q(self, tensor, cb, C, bpp, ab):
        ab = max(4, min(14, ab))
        return self.quant.get((tensor, cb, C, bpp, ab))

    def estimate(self, arch):
        if not self.ok:
            return {"rel_err_expert": None, "rel_err_dense": None, "budget_ratio": None,
                    "precision_verdict": "unknown(precision study not run)"}
        dev = self.device_override or DEVICE_FOR_TECH.get(arch.get("tech"), "generic_1pct")
        cb, C, bpp, ab = arch["cell_bits"], arch["contributors"], arch["bits_per_pass"], arch["adc_bits"]
        out = {"device_model_used": dev}
        worst = 0.0
        for kind, tname in TENSORS.items():
            q = self._q(tname, cb, C, bpp, ab)
            d = self.dev.get(f"{kind}|{dev}|{cb}|{C}|{bpp}")
            if q is None or d is None:
                out[f"rel_err_{kind}"] = None
                worst = None
                continue
            e = math.sqrt(q * q + d * d)
            out[f"rel_err_{kind}"] = e
            out[f"quant_err_{kind}"] = q
            out[f"device_err_{kind}"] = d
            if worst is not None:
                worst = max(worst, e / self.budget[tname])
        out["budget_ratio"] = worst
        if worst is None:
            out["precision_verdict"] = "unknown(config outside sweep)"
        elif worst <= 0.25:
            out["precision_verdict"] = "within_budget"
        elif worst <= 1.0:
            out["precision_verdict"] = "marginal"
        else:
            out["precision_verdict"] = "exceeds_budget"
        return out
