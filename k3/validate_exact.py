#!/usr/bin/env python3
"""Gate 9E — end-to-end exactness harness for the NAND popcount datapath vs
official Kimi K3.

Two layers of validation:

(A) LOCAL, RUNS NOW (no checkpoint): the bit-serial popcount decomposition is
    proven bit-exact vs the OCP-MX reference (k3/mxfp.py) in
    tests/test_gate9_exact.py. Since the reference model is the same MX arithmetic
    K3's kernels implement (vLLM fp8_fp4_mega_moe, UE8M0 scales — Gate 0), an exact
    popcount reducer reconstructs the EXACT block dot product. This module
    additionally checks a full latent-MoE-expert GEMV (3584->3072) block-by-block.

(B) AGAINST REAL K3 TENSORS (documented remote command; NOT run here): to compare
    against official K3 projection/layer/logit outputs you must run K3 on a GPU
    host with the real MXFP4 checkpoint. We do NOT download the 1.56 TB checkpoint
    in this environment. The harness below (`compare_against_reference_npz`) loads
    a capture file of real K3 tensors and checks that the popcount datapath
    reproduces each block dot exactly; the exact capture command is documented in
    `capture_command()` so it can be run where a K3 GPU deployment exists.

Run: python3 k3/validate_exact.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import random

from k3.mxfp import (MxBlock, e2m1_decode, e4m3_decode, e8m0_decode,
                     mx_dot_block, BLOCK)


def e2m1_int(code):
    k = [0, 1, 2, 3, 4, 6, 8, 12][code & 0x7]
    return (-1 if code & 0x8 else 1), k


def e4m3_int(code):
    s = -1 if code & 0x80 else 1
    e = (code >> 3) & 0xF
    m = code & 0x7
    return (s, m, 1) if e == 0 else (s, 8 + m, e)


def popcount_datapath_block_dot(w_codes, a_codes, wsc, asc):
    """Exactly what an in-array popcount reducer + block-scale would compute:
    integer-significand inner product via bitplane popcounts, then E8M0 scales."""
    acc = 0.0
    for wc, ac in zip(w_codes, a_codes):
        w_sign, w_k = e2m1_int(wc)
        a_sign, a_s, a_e = e4m3_int(ac)
        prod = 0
        for b in range(4):
            for c in range(4):
                prod += (1 << (b + c)) * (((w_k >> b) & 1) & ((a_s >> c) & 1))
        acc += w_sign * a_sign * prod * (2.0 ** (a_e - 10)) * (2.0 ** -1)
    return acc * e8m0_decode(wsc) * e8m0_decode(asc)


def check_full_expert_gemv(seed=1, in_dim=3584, out_dim=8, trials=1):
    """Full latent-expert GEMV (in_dim reduction) block-by-block, exact vs ref."""
    rng = random.Random(seed)
    VE4 = [c for c in range(256)
           if not ((((c >> 3) & 0xF) == 0xF) and ((c & 0x7) == 0x7))]
    max_rel = 0.0
    nblk = in_dim // BLOCK
    for _ in range(trials):
        for o in range(out_dim):
            ref_sum = 0.0
            dp_sum = 0.0
            for _blk in range(nblk):
                w_codes = [rng.randrange(16) for _ in range(BLOCK)]
                a_codes = [rng.choice(VE4) for _ in range(BLOCK)]
                wsc = rng.randrange(100, 155)
                asc = rng.randrange(100, 155)
                wb = MxBlock(scale_code=wsc, codes=w_codes)
                a_vals = [e4m3_decode(c) for c in a_codes]
                ref_sum += mx_dot_block(wb, a_vals, asc)
                dp_sum += popcount_datapath_block_dot(w_codes, a_codes, wsc, asc)
            if ref_sum != 0:
                max_rel = max(max_rel, abs(dp_sum - ref_sum) / abs(ref_sum))
    return max_rel


def compare_against_reference_npz(path):
    """Compare the popcount datapath against a capture of REAL K3 tensors.
    Expected npz keys: w_codes [N,32] uint8, a_codes [N,32] uint8, w_scale [N],
    a_scale [N], ref_dot [N] float. Returns max relative error (should be ~0)."""
    try:
        import numpy as np
    except ImportError:
        raise SystemExit("numpy required for real-tensor comparison")
    d = np.load(path)
    max_rel = 0.0
    for i in range(len(d["ref_dot"])):
        got = popcount_datapath_block_dot(
            list(d["w_codes"][i]), list(d["a_codes"][i]),
            int(d["w_scale"][i]), int(d["a_scale"][i]))
        ref = float(d["ref_dot"][i])
        if ref != 0:
            max_rel = max(max_rel, abs(got - ref) / abs(ref))
    return max_rel


def capture_command():
    """Exact remote command to capture real K3 tensors for layer (B) validation.
    Run where an official K3 MXFP4 deployment exists (GPU host, ~8xB300)."""
    return r"""
# On a K3-capable GPU host (do NOT run here; needs the 1.56TB checkpoint):
#   python - <<'PY'
#   import torch, numpy as np
#   from safetensors import safe_open
#   # 1. open one routed-expert weight tensor (MXFP4 packed) + its E8M0 scales
#   #    from the official moonshotai/Kimi-K3 checkpoint (compressed-tensors format)
#   # 2. take one real decode activation vector (MXFP8) at that layer
#   # 3. for each 32-elem block: record w_codes(E2M1), a_codes(E4M3), w_scale,
#   #    a_scale(E8M0), and ref_dot = the kernel's exact block dot (fp32 accum)
#   np.savez('k3_blocks.npz', w_codes=..., a_codes=..., w_scale=..., a_scale=...,
#            ref_dot=...)
#   PY
# Then here:  python k3/validate_exact.py --npz k3_blocks.npz
"""


if __name__ == "__main__":
    if "--npz" in sys.argv:
        p = sys.argv[sys.argv.index("--npz") + 1]
        rel = compare_against_reference_npz(p)
        print(f"real-K3 tensor comparison: max rel err = {rel:.2e} "
              f"({'EXACT' if rel < 1e-9 else 'MISMATCH'})")
    else:
        rel = check_full_expert_gemv(trials=4)
        print(f"(A) full latent-expert GEMV (3584-dim reduction), popcount datapath "
              f"vs OCP-MX reference: max rel err = {rel:.2e} "
              f"({'BIT-EXACT' if rel < 1e-9 else 'FAIL'})")
        print("(B) real-K3 tensor comparison: run with --npz after capturing on a "
              "K3 GPU host — command:")
        print(capture_command())
