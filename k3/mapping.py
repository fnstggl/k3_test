"""K3-specific NAND mapping: expert placement, collision statistics, input reuse.

Two expert-execution strategies:
  wide      : every op (incl. each selected expert) striped across ALL planes,
              executed serially. No placement collisions; pays per-op pipeline
              fill 16x per expert step.
  grouped   : experts statically partitioned into G disjoint plane groups
              (whole channels per group). The 16 selected experts of a layer run
              in parallel across groups; two experts in the same group serialize.
              Expected makespan factor from Monte Carlo over uniform routing
              (Quantile Balancing in K3 makes near-uniform selection a reasonable
              default; skew is a sensitivity knob via `hot_expert_alpha`).
              Replication r>1 stores each expert in r groups; scheduler picks the
              least-loaded replica (power-of-choices), costing r x capacity.

Input reuse: rows_per_page (R) row-segments share a page so one input chunk of
E/R elements serves R rows -> R partial accumulators per plane required (hardware
implication recorded for Gate 4/7).
"""

from dataclasses import dataclass
import math
import random


@dataclass
class K3MappingConfig:
    expert_strategy: str = "grouped"    # 'wide' | 'grouped'
    n_expert_groups: int = 16           # G plane groups for experts
    expert_replication: int = 1         # r copies of each expert
    rows_per_page_expert: int = 8       # R for MXFP4 expert pages
    rows_per_page_dense: int = 4        # R for BF16 dense pages
    hot_expert_alpha: float = 0.0       # 0 = uniform routing; >0 = Zipf skew


def expected_max_group_load(n_groups: int, k_selected: int = 16,
                            n_experts: int = 896, replication: int = 1,
                            alpha: float = 0.0, trials: int = 20000,
                            seed: int = 7) -> float:
    """E[max experts landing in one group] when k experts are drawn without
    replacement from n_experts placed round-robin into n_groups; with
    replication r, each expert has r candidate groups and greedy least-loaded
    assignment is used (power of r choices)."""
    rng = random.Random(seed)
    per_group = n_experts // n_groups
    # expert e lives in groups: (e % n_groups, (e // per_group + e) % n_groups, ...)
    weights = None
    if alpha > 0.0:
        weights = [1.0 / (i + 1) ** alpha for i in range(n_experts)]
    total = 0
    for _ in range(trials):
        if weights is None:
            sel = rng.sample(range(n_experts), k_selected)
        else:
            sel, seen = [], set()
            while len(sel) < k_selected:
                e = rng.choices(range(n_experts), weights=weights)[0]
                if e not in seen:
                    seen.add(e)
                    sel.append(e)
        load = [0] * n_groups
        for e in sel:
            cands = [(e * 7919 + j * 104729) % n_groups for j in range(replication)]
            g = min(cands, key=lambda c: load[c])
            load[g] += 1
        total += max(load)
    return total / trials


def group_geometry(n_channels: int, dies_per_channel: int, planes_per_die: int,
                   n_groups: int) -> dict:
    """Partition the array into G groups along channel boundaries when possible
    (keeps each group's command/broadcast traffic on its own channels)."""
    n_planes = n_channels * dies_per_channel * planes_per_die
    if n_channels >= n_groups:
        ch_per_group = n_channels // n_groups
        return {"channels_per_group": ch_per_group,
                "dies_per_channel_in_group": dies_per_channel,
                "planes_per_group": ch_per_group * dies_per_channel * planes_per_die,
                "plane_fraction": (ch_per_group * dies_per_channel * planes_per_die)
                                  / n_planes}
    # groups smaller than a channel: split within channels (dies per group)
    dies_per_group = max(1, (n_channels * dies_per_channel) // n_groups)
    return {"channels_per_group": 1,
            "dies_per_channel_in_group": dies_per_group,
            "planes_per_group": dies_per_group * planes_per_die,
            "plane_fraction": dies_per_group * planes_per_die / n_planes}


def capacity_required_bytes(storage: dict, mapping: K3MappingConfig) -> float:
    """Expert pool replicated r times; dense pool once."""
    return (storage["expert_bytes"] * mapping.expert_replication
            + storage["dense_bytes"])
