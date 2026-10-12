"""Deterministic single-stream K3 decode scheduler.

Given an architecture description (a flat dict of physical parameters, see
k3cim/architectures.py) and a context length, assign a latency and an energy
to every op of the K3 decode graph (k3cim/workload.py), then

  * token latency  = longest path through the op DAG (true critical path),
  * throughput bounds per shared resource (sense amps / ADCs / orchestrator /
    DRAM) are checked separately and the token time is
        max(critical path, every resource bound),
  * energy/token  = sum over ops (+ static power x token time).

Three execution families are modelled:

  analog_cim   weight-stationary in-situ MVM (3D NAND analog, 3D RRAM, FeNAND)
  digital_nvm  weights read digitally from NVM pages into near-array MAC logic
               (Flash-Cosmos / LLM-on-the-Palm / "HBF"-style digital NAND)
  gpu          roofline + per-layer overhead, calibrated to measured data

Every op latency is explicit, so the same graph gives the per-layer
latency breakdown written to results/latency_breakdown.csv.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .workload import BYTES_PER_WEIGHT, K3Workload, Op

NONLIN_KINDS = {"norm", "attnres", "router_topk", "softmax", "combine", "act", "add",
                "headnorm", "conv", "sample", "embed"}


# ----------------------------------------------------------------------------- helpers
def adc_energy_j(bits, p):
    """ADC energy per conversion: max(Walden FoM * 2^bits, thermal-noise-limited Schreier bound)."""
    walden = p["adc_fom_j_per_step"] * 2 ** bits
    # Schreier FoM_S (dB) = SNDR + 10log10(BW/P)  ->  E = 2^(2b) * 1.5 * kT-ish; use explicit thermal floor
    thermal = p.get("adc_thermal_coeff_j", 8 * 1.38e-23 * 300) * (2 ** (2 * bits)) * 1.5
    return max(walden, thermal)


def adc_time_s(bits, p):
    """SAR-style conversion time: (bits + overhead cycles) * bit-cycle time."""
    return (bits + p.get("adc_overhead_cycles", 2)) * p["adc_bit_cycle_s"]


def adc_area_m2(bits, p):
    """ADC area: fixed logic + capacitor/DAC part scaling 2^bits (matching / kT/C limited)."""
    return p["adc_area_fixed_m2"] + p["adc_area_per_level_m2"] * 2 ** bits


def expected_max_load(n_balls_groups, group_size, n_bins, n_items_total, trials=200, seed=0):
    """Expected max number of *active* tiles landing on one array.

    n_items_total experts, each split into group_size tiles placed on distinct bins
    (random placement); n_balls_groups experts active. Returns E[max load] >= 1.
    """
    if n_balls_groups == 0:
        return 0.0
    rng = np.random.default_rng(seed)
    if group_size >= n_bins:
        return math.ceil(n_balls_groups * group_size / n_bins)
    loads_max = []
    for _ in range(trials):
        load = np.zeros(n_bins, np.int32)
        for _e in range(n_balls_groups):
            load[rng.choice(n_bins, group_size, replace=False)] += 1
        loads_max.append(load.max())
    return float(np.mean(loads_max))


@dataclass
class OpCost:
    latency: float
    energy: float
    breakdown: dict


# ============================================================================= model
class Scheduler:
    def __init__(self, arch: dict, wl: K3Workload | None = None):
        self.p = arch
        self.wl = wl or K3Workload(fold_mla=arch.get("fold_mla", False),
                                   kv_bytes=arch.get("kv_bytes", 2.0),
                                   kda_state_bytes=arch.get("kda_state_bytes", 4.0))
        self._expert_rounds = None
        self._group_tiles = None

    # ------------------------------------------------------------- representations
    def w_bits(self, op):
        p = self.p
        if op.wdtype == "mxfp4":
            return p["expert_w_mag_bits"]
        return p["dense_w_mag_bits"]

    def bytes_per_weight_digital(self, op):
        p = self.p
        if op.wdtype == "mxfp4":
            return BYTES_PER_WEIGHT["mxfp4"]
        return p.get("dense_bytes_per_weight", 2.0)

    def slices(self, op):
        return max(1, math.ceil(self.w_bits(op) / self.p["cell_bits"]))

    # ------------------------------------------------------------- comms
    def kv_bytes_at(self, L):
        """MLA latent KV bytes at context L in this architecture's KV format (arch kv_bytes per value)."""
        return self.wl.kv_cache_bytes(L) * self.p.get("kv_bytes", 2.0) / self.wl.kv_bytes

    def t_link(self, bits, kind):
        p = self.p
        return p[f"{kind}_latency_s"] + bits / p[f"{kind}_bw_bps"]

    def e_link(self, bits, kind):
        return bits * self.p[f"{kind}_pj_per_bit"] * 1e-12

    # ------------------------------------------------------------- orchestrator ops
    def nonlinear_cost(self, op: Op, L):
        p = self.p
        bd = {}
        if op.kind in ("attn_score", "attn_value"):
            macs = op.K * op.N * L
            kv_bytes = (op.K * L * p.get("kv_bytes", 2.0)) if op.kind == "attn_score" else 0.0
            # value pass re-reads the 512-d latent part (already counted once in score if fused)
            if op.kind == "attn_value" and not p.get("fused_mla_attention", True):
                kv_bytes = op.K * L * p.get("kv_bytes", 2.0)
            t_c = 2 * macs / p["attn_flops"]
            t_m = kv_bytes / p["kv_bw_Bps"]
            lat = p["orch_op_latency_s"] + max(t_c, t_m)
            e = 2 * macs * p["attn_pj_per_flop"] * 1e-12 + kv_bytes * 8 * p["kv_pj_per_bit"] * 1e-12
            bd = {"attn_compute": t_c, "kv_read": t_m}
            return OpCost(lat, e, bd)
        if op.kind == "softmax":
            n = op.elems * L
            lat = p["orch_op_latency_s"] + n / p["orch_vec_ops"]
            return OpCost(lat, n * p["orch_pj_per_op"] * 1e-12, {"softmax": lat})
        if op.kind == "kda_recurrent":
            flops = 8 * op.elems                         # 4 passes over the d x d state, MAC=2 flop
            state_b = op.elems * p.get("kda_state_bytes", 4.0) * 2  # read + write
            t_c = flops / p["kda_flops"]
            t_m = state_b / p["kda_state_bw_Bps"]
            lat = p["orch_op_latency_s"] + max(t_c, t_m)
            e = flops * p["orch_pj_per_op"] * 1e-12 + state_b * 8 * p["kda_state_pj_per_bit"] * 1e-12
            return OpCost(lat, e, {"kda_compute": t_c, "kda_state": t_m})
        if op.kind == "embed":
            lat = p["embed_latency_s"]
            return OpCost(lat, op.elems * 16 * p["kv_pj_per_bit"] * 1e-12, {"embed": lat})
        if op.kind == "sample":
            lat = p["orch_op_latency_s"] + op.elems / p["orch_vec_ops"] + p["host_latency_s"]
            return OpCost(lat, op.elems * p["orch_pj_per_op"] * 1e-12, {"sample": lat})
        # norms / reductions / elementwise. Global reductions need the full vector at one place.
        n = op.elems
        fixed = p["orch_op_latency_s"]
        if op.kind in ("add", "act", "headnorm", "conv") and p["family"] != "gpu":
            fixed *= 0.25     # elementwise: fused into the orchestrator datapath, no global gather/sync
        lat = fixed + n / p["orch_vec_ops"]
        if op.kind in ("norm", "attnres", "combine", "router_topk") and p.get("fold_norm_scale", False) \
                and op.kind == "norm":
            lat = p["orch_op_latency_s"]   # rms applied post-MVM (scalar), off the critical path
        return OpCost(lat, n * p["orch_pj_per_op"] * 1e-12, {op.kind: lat})

    # ------------------------------------------------------------- analog CIM linear op
    def analog_linear_cost(self, op: Op):
        p = self.p
        C = p["contributors"]
        cols = p["array_cols"]
        nsl = self.slices(op)
        diff = 2 if p["signed_mode"] == "differential" else 1
        cpw = nsl * diff                                   # cells per weight
        groups = math.ceil(op.K / C)
        # conversions: outputs x groups x slices x (pos/neg digitised separately?) x steps
        sub_analog = p.get("analog_subtract", True)
        conv_per_step = op.N * op.count * groups * nsl * (1 if (sub_analog or diff == 1) else 2)
        bits_x = p["x_mag_bits"]
        s = p["bits_per_pass"]
        passes = math.ceil(bits_x / s)
        sign_phases = 2 if p.get("input_sign_phases", True) else 1
        analog_acc = p.get("analog_accumulate_passes", False)
        steps = passes * sign_phases
        conv_steps = sign_phases if analog_acc else steps
        conversions = conv_per_step * conv_steps
        # array-ops (tiles): one WL layer x C strings x cols bitlines per op
        cells = op.K * op.N * op.count * cpw
        tiles = math.ceil(cells / (C * cols))
        # rounds from conflicts
        if op.always_active:
            rounds = 1.0 if tiles <= p["arrays_per_stage_limit"] else math.ceil(tiles / p["arrays_per_stage_limit"])
        else:
            rounds = self.expert_rounds(op, tiles)
        # per array op time
        # one analog sum per bitline; a differential pair subtracted in analog -> 1 conversion
        conv_per_array_per_step = cols // 2 if (diff == 2 and sub_analog) else cols
        adcs = min(self.adcs_per_active_array(op), conv_per_array_per_step)
        adc_bits = p["adc_bits"]
        t_conv = adc_time_s(adc_bits, p)
        t_int = (2 ** s - 1) * p["t_unit_s"] if p.get("time_encoded_input", True) else p["t_dac_settle_s"]
        if analog_acc:
            # integrate all passes on the capacitor, convert once per sign phase
            t_steps = steps * (p["t_step_fixed_s"] + t_int) + conv_steps * math.ceil(
                conv_per_array_per_step / adcs) * t_conv
        else:
            t_steps = steps * (p["t_step_fixed_s"] + t_int + math.ceil(conv_per_array_per_step / adcs) * t_conv)
        if op.always_active:
            wl_frac = p.get("wl_exposed_frac_dense", 0.0)
        elif op.name.endswith("expert_w2"):
            wl_frac = 0.0     # w2 word lines are biased while w1/w3 compute (expert ids already known)
        else:
            wl_frac = p.get("wl_exposed_frac_expert", 1.0)
        wl = p["t_wl_s"] * wl_frac
        t_arr = wl + t_steps
        t_array_total = rounds * t_arr
        # communication
        # experts w1/w3 share the latent input (broadcast once); w2 inputs differ per expert
        in_bits = op.K * (bits_x + 1) * (op.count if op.name.endswith("expert_w2") else 1)
        out_bits = op.N * op.count * p["psum_bits"]
        t_in = self.t_link(in_bits / p.get("bcast_fanout_share", 1.0), "die_in")
        t_out = self.t_link(out_bits / max(1, min(p.get("dies_total", p["dies_per_op"]), tiles)), "die_out") \
            + out_bits / p["orch_in_bw_bps"]
        t_red = p["htree_levels"] * p["t_htree_hop_s"]
        lat = t_in + t_array_total + t_red + t_out + p["digital_scale_latency_s"]
        # energy
        e_conv = conversions * adc_energy_j(adc_bits, p)
        e_wl = tiles * p["e_wl_per_op_j"] * (1.0 if op.always_active else 1.0)
        e_bl = tiles * steps * cols * p["e_bl_per_step_j"]
        i_avg = p["i_cell_max_a"] * p["avg_level_frac"] * p["avg_input_bit_frac"]
        e_cell = cells * i_avg * p["v_bl"] * (steps * (t_int + p["t_step_fixed_s"]))
        e_dig = conversions * p["e_shiftadd_per_conv_j"]
        e_drv = tiles * steps * C * p["e_input_driver_per_bit_j"] * p["avg_input_bit_frac"]
        dies_part = max(1, min(p.get("dies_total", p["dies_per_op"]), tiles))
        e_com = self.e_link(in_bits * dies_part, "die_in") + self.e_link(out_bits, "die_out")
        if "e_array_op_j" in p:
            # simulator-calibrated energy per array MVM (NeuroSim: incl. ADC + shift-add), scaled by passes
            e_conv = tiles * p["e_array_op_j"] * (steps / 8.0)
            e_wl = e_bl = e_cell = e_dig = e_drv = 0.0
        e = e_conv + e_wl + e_bl + e_cell + e_dig + e_drv + e_com
        bd = {"t_in": t_in, "t_array": t_array_total, "t_reduce": t_red, "t_out": t_out,
              "t_wl_round": wl, "t_steps_round": t_steps, "in_bits": in_bits, "out_bits": out_bits,
              "rounds": rounds, "tiles": tiles, "conversions": conversions, "steps": steps,
              "e_adc": e_conv, "e_wl": e_wl, "e_bl": e_bl, "e_cell": e_cell, "e_digital": e_dig,
              "e_driver": e_drv, "e_comm": e_com}
        return OpCost(lat, e, bd)

    def concurrent_tiles(self, op):
        """Tiles of all linear ops that start together with `op` (same layer, same dependencies)."""
        if self._group_tiles is None:
            p = self.p
            groups = defaultdict(list)
            for o in self.wl.linear_ops():
                groups[(o.layer, tuple(sorted(o.deps)))].append(o)
            self._group_tiles = {}
            for ops in groups.values():
                tot = 0
                for o in ops:
                    nsl = self.slices(o)
                    cells = o.K * o.N * o.count * nsl * (2 if p["signed_mode"] == "differential" else 1)
                    tot += math.ceil(cells / (p["contributors"] * p["array_cols"]))
                for o in ops:
                    self._group_tiles[o.name] = tot
        return self._group_tiles[op.name]

    def adcs_per_active_array(self, op):
        p = self.p
        if p.get("adc_sharing", "per_plane") == "die_pool":
            act = self.concurrent_tiles(op)
            per_die = math.ceil(act / max(1, p["dies_total"]))
            return max(1, p["adc_pool_per_die"] // max(1, per_die))
        return p["adcs_per_array"]

    def expert_rounds(self, op, tiles):
        if "expert_rounds_override" in self.p:
            return self.p["expert_rounds_override"]
        if self._expert_rounds is None:
            self._expert_rounds = {}
        key = (op.name.split(".")[-1], tiles)
        if key not in self._expert_rounds:
            p = self.p
            per_expert = max(1, tiles // op.count)
            bins = p["expert_arrays_per_layer"]
            self._expert_rounds[key] = max(1.0, expected_max_load(op.count, per_expert, bins, op.stored,
                                                                  trials=p.get("mc_trials", 100)))
        return self._expert_rounds[key]

    # ------------------------------------------------------------- digital NVM linear op
    def digital_linear_cost(self, op: Op):
        p = self.p
        bpw = self.bytes_per_weight_digital(op)
        wbytes = op.K * op.N * op.count * bpw
        pages = math.ceil(wbytes / p["page_bytes"])
        planes = p["planes_total"]
        # data-dependent pages (experts) incur tR on the critical path; dense ops are prefetched
        t_read = p["t_read_s"] if not op.always_active else p["t_read_s"] * p.get("dense_read_exposed_frac", 0.0)
        # near-plane compute: each plane processes its pages; pages spread over planes
        pages_per_plane = math.ceil(pages / min(pages, planes))
        t_comp = pages_per_plane * (p["page_bytes"] / bpw) / p["plane_mac_rate"]
        if pages_per_plane > p.get("page_buffers_per_plane", 1):
            # extra pages must be read during the op
            t_comp = max(t_comp, (pages_per_plane - p.get("page_buffers_per_plane", 1)) * p["t_read_s"] + t_comp)
        in_bits = op.K * 16 * (op.count if op.name.endswith("expert_w2") else 1)
        out_bits = op.N * op.count * p["psum_bits"]
        t_in = self.t_link(in_bits, "die_in")
        t_out = self.t_link(out_bits / max(1, min(p.get("dies_total", p["dies_per_op"]), pages)), "die_out") \
            + out_bits / p["orch_in_bw_bps"]
        t_red = p["htree_levels"] * p["t_htree_hop_s"]
        lat = t_in + t_read + t_comp + t_red + t_out
        e_read = pages * p["e_page_read_j"]
        e_mac = op.K * op.N * op.count * p["e_mac_j"]
        dies_part = max(1, min(p.get("dies_total", p["dies_per_op"]), pages))
        e_com = self.e_link(in_bits * dies_part, "die_in") + self.e_link(out_bits, "die_out")
        bd = {"t_in": t_in, "t_read": t_read, "t_compute": t_comp, "t_reduce": t_red, "t_out": t_out,
              "pages": pages, "e_read": e_read, "e_mac": e_mac, "e_comm": e_com}
        return OpCost(lat, e_read + e_mac + e_com, bd)

    # ------------------------------------------------------------- GPU
    def gpu_linear_cost(self, op: Op):
        p = self.p
        bpw = self.bytes_per_weight_digital(op)
        wbytes = op.K * op.N * op.count * bpw
        t_m = wbytes / (p["gpu_mem_bw_Bps"] * p["gpu_bw_efficiency"])
        t_c = 2 * op.K * op.N * op.count / (p["gpu_flops"] * p["gpu_flop_efficiency"])
        lat = p["gpu_kernel_latency_s"] + max(t_m, t_c)
        e = wbytes * 8 * p["gpu_mem_pj_per_bit"] * 1e-12 + 2 * op.K * op.N * op.count * p["gpu_pj_per_flop"] * 1e-12
        return OpCost(lat, e, {"t_mem": t_m, "t_compute": t_c})

    # ------------------------------------------------------------- per op dispatch
    def op_cost(self, op: Op, L):
        fam = self.p["family"]
        if op.kind == "linear":
            if fam == "analog_cim":
                if op.wdtype == "bf16" and self.p.get("dense_on_gpu_like", False):
                    return self.gpu_linear_cost(op)
                return self.analog_linear_cost(op)
            if fam == "digital_nvm":
                return self.digital_linear_cost(op)
            if fam == "gpu":
                return self.gpu_linear_cost(op)
        c = self.nonlinear_cost(op, L)
        if fam == "gpu":
            c = OpCost(c.latency + self.p["gpu_kernel_latency_s"] * self.p.get("gpu_nonlin_kernel_frac", 0.3),
                       c.energy, c.breakdown)
        return c

    # ------------------------------------------------------------- token evaluation
    def evaluate(self, L, detail=False):
        p = self.p
        costs = {o.name: self.op_cost(o, L) for o in self.wl.ops}
        t_cp, path = self.wl.critical_path_ops(lambda o: costs[o.name].latency)
        # extra per-layer synchronisation (GPU: collectives, NVM: control)
        t_cp += p.get("per_layer_sync_s", 0.0) * self.wl.nL + p.get("per_token_overhead_s", 0.0)
        bounds = self.resource_bounds(L, costs)
        t_tok = max([t_cp] + list(bounds.values()))
        e_dyn = sum(c.energy for c in costs.values())
        static_w = p.get("static_power_w", 0.0)
        if p["family"] in ("analog_cim", "digital_nvm"):
            static_w = p.get("orch_static_w", 10.0) + p.get("dies_total", 0) * p.get("nvm_die_static_w", 0.005)
        if p.get("kv_in_sram"):
            from .architectures import SRAM_LEAK_W_PER_GB
            static_w += SRAM_LEAK_W_PER_GB * (self.kv_bytes_at(L) + self.wl.kda_state_bytes_total()) / 1e9
        e_static = static_w * t_tok
        out = {"context": L, "t_token_s": t_tok, "tok_per_s": 1.0 / t_tok, "t_critical_path_s": t_cp,
               "bounds": bounds, "energy_j_per_token": e_dyn + e_static, "e_dynamic_j": e_dyn,
               "e_static_j": e_static, "power_w": (e_dyn + e_static) / t_tok}
        if detail:
            out["costs"] = costs
            out["path"] = path
        return out

    def resource_bounds(self, L, costs):
        """Token-time lower bounds from aggregate resource throughput (not latency)."""
        p, wl = self.p, self.wl
        b = {}
        fam = p["family"]
        if fam == "digital_nvm":
            bytes_tok = sum(o.K * o.N * o.count * self.bytes_per_weight_digital(o) for o in wl.linear_ops())
            pages = bytes_tok / p["page_bytes"]
            b["nvm_sense_throughput"] = pages * p["t_read_s"] / p["planes_total"]
        if p.get("weights_cross_io"):
            bytes_tok = sum(o.K * o.N * o.count * self.bytes_per_weight_digital(o) for o in wl.linear_ops())
            b["nvm_io_bandwidth"] = bytes_tok * 8 / (p["dies"] * p["die_in_bw_bps"])
        if fam == "analog_cim":
            conv = sum(c.breakdown.get("conversions", 0) for c in costs.values())
            adc_total = (p["adc_pool_per_die"] * p["dies_total"] if p.get("adc_sharing") == "die_pool"
                         else p["adcs_per_array"] * p["arrays_total"])
            b["adc_throughput"] = conv * adc_time_s(p["adc_bits"], p) / (adc_total * p.get("adc_util_max", 0.5))
        if fam == "gpu":
            bytes_tok = sum(o.K * o.N * o.count * self.bytes_per_weight_digital(o) for o in wl.linear_ops())
            b["hbm_bw"] = bytes_tok / (p["gpu_mem_bw_Bps"] * p["gpu_bw_efficiency"])
        # KV-cache bandwidth & attention compute are on the critical path already;
        # report them as bounds too for transparency
        att_macs = sum(o.K * o.N * L for o in wl.ops if o.kind in ("attn_score", "attn_value"))
        b["attention_compute"] = 2 * att_macs / p["attn_flops"]
        b["kv_bandwidth"] = self.kv_bytes_at(L) / p["kv_bw_Bps"]
        if p.get("power_cap_w"):
            pass
        return b

    # ------------------------------------------------------------- per-layer breakdown
    def layer_breakdown(self, L):
        r = self.evaluate(L, detail=True)
        costs, path = r["costs"], set(r["path"])
        rows = defaultdict(lambda: defaultdict(float))
        for o in self.wl.ops:
            c = costs[o.name]
            key = o.layer
            cat = self.category(o)
            if o.name in path:
                rows[key]["cp_" + cat] += c.latency
            rows[key]["energy_" + cat] += c.energy
        return r, rows

    @staticmethod
    def category(o: Op):
        if o.kind == "linear":
            part = o.name.split(".")[1] if "." in o.name else o.name
            if part == "moe":
                return "moe_expert_mvm" if not o.always_active else "moe_dense_mvm"
            if part in ("kda", "mla"):
                return "attn_proj_mvm"
            if part == "mlp":
                return "dense_mlp_mvm"
            return "lm_head_mvm"
        if o.kind in ("attn_score", "attn_value", "softmax"):
            return "mla_attention"
        if o.kind in ("kda_recurrent", "conv", "headnorm"):
            return "kda_recurrence"
        if o.kind in ("norm", "attnres", "add"):
            return "norm_residual"
        if o.kind in ("router_topk", "combine"):
            return "routing"
        return "other"


# ============================================================================= extensions
def spec_tokens_per_step(alpha, k):
    """Expected tokens emitted per verification step with k drafts and per-token acceptance alpha."""
    return (1 - alpha ** (k + 1)) / (1 - alpha) if alpha < 1 else k + 1


def fit_alpha(tau, k):
    """Per-token acceptance reproducing a measured acceptance length tau with k drafts."""
    lo, hi = 0.0, 0.999
    for _ in range(60):
        mid = (lo + hi) / 2
        if spec_tokens_per_step(mid, k) < tau:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


ALPHA_DSPARK = None


def speculative_tok_per_s(sched: "Scheduler", L, k, alpha=None, t_draft_per_token=1.0e-3):
    """Single-user tok/s with k draft tokens verified per step.

    Verification of V = k+1 positions:
      GPU / digital-NVM: weights are read once per step (bandwidth-bound) -> weight-time ~unchanged,
                         compute x V, attention compute x V, KV read once;
      analog CIM:        every array op processes one vector -> array time x V, link payload x V;
      KDA recurrence and norms: x V (sequential dependency inside the step, small).
    alpha defaults to the value fitted to the measured DSpark acceptance on K3
    (3.84 tokens per step with 7 drafts, vLLM, DGX B300; llm_decode_benchmarks_sourced.csv).
    t_draft_per_token = 1 ms reproduces the measured 188 tok/s (DSpark, k=7) with the calibrated GPU model.
    """
    global ALPHA_DSPARK
    if alpha is None:
        if ALPHA_DSPARK is None:
            ALPHA_DSPARK = fit_alpha(3.84, 7)
        alpha = ALPHA_DSPARK
    V = k + 1
    p = sched.p
    fam = p["family"]
    # V tokens touch the union of their routed experts: E[distinct]/16 more expert weights
    frac = 16.0 / 896.0
    D = 896.0 * (1 - (1 - frac) ** V) / 16.0
    costs = {}
    for o in sched.wl.ops:
        c = sched.op_cost(o, L)
        lat = c.latency
        if o.kind == "linear":
            if fam == "analog_cim":
                b = c.breakdown
                lat = lat + (V - 1) * (b.get("t_array", 0.0) + b.get("t_in", 0.0) + b.get("t_out", 0.0))
            elif fam == "gpu":
                lat = lat + (V - 1) * c.breakdown.get("t_compute", 0.0)
                if not o.always_active:
                    lat = lat + (D - 1) * c.breakdown.get("t_mem", 0.0)
            else:
                lat = lat + (V - 1) * c.breakdown.get("t_compute", 0.0)
                if not o.always_active:
                    lat = lat + (D - 1) * (c.breakdown.get("t_compute", 0.0))
        elif o.kind in ("attn_score", "attn_value"):
            lat = lat + (V - 1) * c.breakdown.get("attn_compute", 0.0)
        elif o.kind == "kda_recurrent":
            lat = lat + (V - 1) * c.breakdown.get("kda_compute", 0.0)
        elif o.kind in ("norm", "attnres", "router_topk", "combine", "softmax"):
            lat = lat * (1 + 0.25 * (V - 1))
        costs[o.name] = lat
    t, _ = sched.wl.critical_path_ops(lambda o: costs[o.name])
    t += p.get("per_layer_sync_s", 0.0) * sched.wl.nL + t_draft_per_token * k
    if fam in ("gpu", "digital_nvm"):
        # throughput bound of the expert weight stream grows with D
        exp_b = sum(o.K * o.N * o.count * sched.bytes_per_weight_digital(o) for o in sched.wl.linear_ops()
                    if not o.always_active)
        den_b = sum(o.K * o.N * o.count * sched.bytes_per_weight_digital(o) for o in sched.wl.linear_ops()
                    if o.always_active)
        if fam == "gpu":
            t = max(t, (den_b + D * exp_b) / (p["gpu_mem_bw_Bps"] * p["gpu_bw_efficiency"]))
        else:
            t = max(t, (den_b + D * exp_b) / p["page_bytes"] * p["t_read_s"] / p["planes_total"])
    return spec_tokens_per_step(alpha, k) / t, t


# Measured on real K3 routing (layers 1-3, 16-token text, data/k3/activations/k3_layers0-3.npz):
# for a window of V consecutive tokens, mean over windows and layers of
#   distinct experts / 16           and   max number of the V tokens routed to one expert.
# Random routing would give D = 896(1-(1-16/896)^V)/16 and max-load ~1-2; real routing reuses
# experts across neighbouring tokens (adjacent-token overlap 1.6-4.9 of 16 vs 0.29 random).
ROUTING_LOCALITY_MEASURED = {1: (1.0, 1.0), 2: (1.81, 1.88), 4: (3.26, 3.11), 8: (5.76, 5.50)}


def _interp_locality(V):
    ks = sorted(ROUTING_LOCALITY_MEASURED)
    if V in ROUTING_LOCALITY_MEASURED:
        return ROUTING_LOCALITY_MEASURED[V]
    if V > ks[-1]:
        d, m = ROUTING_LOCALITY_MEASURED[ks[-1]]
        return d * V / ks[-1], m * V / ks[-1]
    lo = max(k for k in ks if k < V)
    hi = min(k for k in ks if k > V)
    f = (V - lo) / (hi - lo)
    a, b = ROUTING_LOCALITY_MEASURED[lo], ROUTING_LOCALITY_MEASURED[hi]
    return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])


def speculative_cim(sched: "Scheduler", L, k, dense_replicas=1, alpha=None, t_draft_per_token=None,
                    routing="measured"):
    """Speculative decoding on a weight-stationary analog CIM (extension; hypothetical drafter).

    One verification step processes V = k+1 token vectors through every layer:
      * always-active (dense) arrays: ceil(V / dense_replicas) vector ops per array; the word-line
        selection is kept, only the input/integration/conversion steps repeat;
      * routed experts: the union of the V tokens' experts is active (more slot conflicts) and an
        expert chosen by m of the V tokens performs m vector ops in series (m = measured max load);
      * activation links carry V vectors; attention compute x V (KV read once); KDA recurrence x V;
      * ADC throughput and attention-compute bounds x V.
    The drafter defaults to an EAGLE-class one-layer head run on the same hardware: one average
    K3 layer + the LM head per draft token (assumption - no such K3 drafter is public; acceptance
    alpha is fitted to the measured DSpark acceptance on K3, tau = 3.84 at k = 7).
    Returns dict(tok_per_s, t_step_s, tau, V, J_per_token, details).
    """
    global ALPHA_DSPARK
    if alpha is None:
        if ALPHA_DSPARK is None:
            ALPHA_DSPARK = fit_alpha(3.84, 7)
        alpha = ALPHA_DSPARK
    p, wl = sched.p, sched.wl
    assert p["family"] == "analog_cim"
    V = k + 1
    if routing == "measured":
        Drel, m = _interp_locality(V)
    else:
        Drel = 896.0 * (1 - (1 - 16.0 / 896.0) ** V) / 16.0
        m = 1.0 + (V - 1) * 16.0 / 896.0
    base = sched.evaluate(L, detail=True)
    costs1 = base["costs"]
    reps = max(1, int(dense_replicas))
    # expert slot conflicts with 16*Drel distinct active experts
    tpe = p.get("tiles_per_expert")
    if tpe is None:
        tpe = math.ceil(2 * 3584 * 3072 * math.ceil(p["expert_w_mag_bits"] / p["cell_bits"]) * 2
                        / (p["contributors"] * p["array_cols"]))
    from .architectures import structured_expert_rounds
    r1 = p.get("expert_rounds_override") or 1.0
    rV = max(r1, structured_expert_rounds(int(round(16 * Drel)), tpe, p.get("expert_planes", p["planes"]), 896))
    costs = {}
    for o in wl.ops:
        c = costs1[o.name]
        lat = c.latency
        b = c.breakdown
        if o.kind == "linear" and "t_steps_round" in b:
            f = p.get("bcast_fanout_share", 1.0)
            extra_in = (V - 1) * b["in_bits"] / f / p["die_in_bw_bps"]
            den = max(1, min(p.get("dies_total", p["dies_per_op"]), b["tiles"]))
            extra_out = (V - 1) * b["out_bits"] * (1.0 / den / p["die_out_bw_bps"] + 1.0 / p["orch_in_bw_bps"])
            if o.always_active:
                vec = math.ceil(V / reps)
                lat = lat + (vec - 1) * b["rounds"] * b["t_steps_round"]
            else:
                rounds = b["rounds"] * rV / r1
                lat = lat + (rounds - b["rounds"]) * (b["t_wl_round"] + b["t_steps_round"]) \
                    + (m - 1) * b["t_steps_round"]
            lat += extra_in + extra_out
        elif o.kind in ("attn_score", "attn_value"):
            lat = lat + (V - 1) * b.get("attn_compute", 0.0)
        elif o.kind == "kda_recurrent":
            lat = lat + (V - 1) * b.get("kda_compute", 0.0)
        elif o.kind in ("norm", "attnres", "router_topk", "combine", "softmax"):
            lat = lat * (1 + 0.25 * (V - 1))
        costs[o.name] = lat
    t_cp, _ = wl.critical_path_ops(lambda o: costs[o.name])
    t_cp += p.get("per_layer_sync_s", 0.0) * wl.nL + p.get("per_token_overhead_s", 0.0)
    if t_draft_per_token is None:
        lm = sum(costs1[o.name].latency for o in wl.ops if o.name.startswith("lm_head"))
        t_draft_per_token = (base["t_critical_path_s"] - lm) / wl.nL + lm
    t_draft = k * t_draft_per_token
    bounds = {kk: v * (V if kk in ("adc_throughput", "attention_compute") else 1.0)
              for kk, v in base["bounds"].items()}
    t_step = max([t_cp + t_draft] + list(bounds.values()))
    tau = spec_tokens_per_step(alpha, k)
    static_w = p.get("orch_static_w", 10.0) + p.get("dies_total", 0) * p.get("nvm_die_static_w", 0.005)
    e_step = base["e_dynamic_j"] * (V + k * 1.0 / wl.nL) + static_w * t_step
    return {"tok_per_s": tau / t_step, "t_step_s": t_step, "tau": tau, "V": V, "k": k,
            "dense_replicas": reps, "t_critical_path_s": t_cp, "t_draft_s": t_draft,
            "J_per_token": e_step / tau, "bounds": bounds, "expert_rounds_V": rV, "max_load": m}


def with_dense_replicas(arch, R):
    """Copy of an analog-CIM architecture with R copies of every always-active (dense) weight."""
    from .architectures import weight_cells
    a = dict(arch)
    if R <= 1:
        return a
    wl = K3Workload(fold_mla=arch.get("fold_mla", False))
    cb = arch["cell_bits"]
    dense_cells = 0
    for o in wl.linear_ops():
        if o.wdtype != "mxfp4":
            dense_cells += o.stored_weights * math.ceil(arch["dense_w_mag_bits"] / cb) * 2
    dense_cells *= 1.08
    cpp = arch["array_rows"] * arch["array_cols"] * arch["array_stacks"]
    add_planes = math.ceil((R - 1) * dense_cells / cpp)
    a["expert_planes"] = arch.get("expert_planes", arch["planes"])
    a["planes"] = arch["planes"] + add_planes
    a["arrays_total"] = arch["arrays_total"] + add_planes
    a["cells_total"] = arch["cells_total"] + (R - 1) * dense_cells
    ppd = arch.get("planes_per_die", 256)
    a["dies_total"] = max(1, math.ceil(a["planes"] / ppd))
    a["dense_replicas"] = R
    a["name"] = f"{arch['name']}_x{R}dense"
    return a


def prefill_seconds(sched: "Scheduler", T, reuse_tokens_per_read=64):
    """Time-to-first-token estimate for a T-token prompt (throughput-bound, pipelined over layers)."""
    p, wl = sched.p, sched.wl
    fam = p["family"]
    macs_lin = sum(o.macs for o in wl.ops)
    att_macs = sum(o.K * o.N for o in wl.ops if o.kind in ("attn_score", "attn_value")) * T * (T + 1) / 2
    t_att = 2 * att_macs / p["attn_flops"]
    if fam == "gpu":
        t_lin = 2 * macs_lin * T / (p["gpu_flops"] * 0.5)
    elif fam == "digital_nvm":
        bytes_tok = sum(o.K * o.N * o.count * sched.bytes_per_weight_digital(o) for o in wl.linear_ops())
        # dense weights read once per batch of prompt tokens; experts: union of routed experts ~ all for big T
        reads = math.ceil(T / reuse_tokens_per_read)
        t_sense = reads * bytes_tok / p["page_bytes"] * p["t_read_s"] / p["planes_total"]
        t_mac = macs_lin * T / (p["planes_total"] * p["plane_mac_rate"])
        t_lin = max(t_sense, t_mac)
    else:
        # weight-stationary: each prompt token needs its own array op on every tile it uses
        tiles_tok, conv_tok, t_arr_w = 0.0, 0.0, 0.0
        for o in wl.linear_ops():
            c = sched.analog_linear_cost(o)
            tiles_tok += c.breakdown["tiles"]
            conv_tok += c.breakdown["conversions"]
            t_arr_w += c.breakdown["tiles"] * c.breakdown["t_array"] / max(c.breakdown["rounds"], 1)
        t_arr_avg = t_arr_w / tiles_tok
        t_occ = tiles_tok * t_arr_avg / p["arrays_total"]
        adc_total = (p["adc_pool_per_die"] * p["dies_total"] if p.get("adc_sharing") == "die_pool"
                     else p["adcs_per_array"] * p["arrays_total"])
        t_adc = conv_tok * adc_time_s(p["adc_bits"], p) / adc_total
        t_lin = T * max(t_occ, t_adc)
    return t_lin + t_att, {"t_linear": t_lin, "t_attention": t_att}
