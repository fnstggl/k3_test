"""Fetch individual Kimi-K3 tensors from HuggingFace via HTTP byte ranges.

Each tensor is located with the cached safetensors JSON headers (see
scripts/fetch_k3_manifest.py) and downloaded once into .cache/k3_tensors/.
BF16 tensors are returned as exact float32 arrays; U8/F32 as stored.
"""
import json
import os
import subprocess
import time

import numpy as np

REPO = "moonshotai/Kimi-K3"
REV = "f831ab66814297da540d832a5235f8e904f29d06"
BASE = f"https://huggingface.co/{REPO}/resolve/{REV}/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HDR_DIR = os.path.join(ROOT, ".cache", "k3_headers")
TEN_DIR = os.path.join(ROOT, ".cache", "k3_tensors")

_index = None
_headers = {}


def _weight_map():
    global _index
    if _index is None:
        _index = json.load(open(os.path.join(HDR_DIR, "model.safetensors.index.json")))["weight_map"]
    return _index


def _header(fname):
    if fname not in _headers:
        raw = open(os.path.join(HDR_DIR, fname + ".json"), "rb").read()
        _headers[fname] = (len(raw), json.loads(raw))
    return _headers[fname]


def _curl_range(url, start, end, out, tries=8):
    """Download bytes [start, end] with retries/backoff (HF rate-limits bursts)."""
    for i in range(tries):
        r = subprocess.run(["curl", "-sSL", "--fail", "--retry", "3", "--retry-all-errors",
                            "-r", f"{start}-{end}", "-o", out, url], capture_output=True)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) == end - start + 1:
            return
        time.sleep(min(60, 2 ** i))
    raise IOError(f"failed to fetch {url} [{start}-{end}]: {r.stderr[-300:]}")


def bf16_to_f32(u16):
    return (u16.astype(np.uint32) << 16).view(np.float32)


def tensor_info(name):
    fname = _weight_map()[name]
    hl, h = _header(fname)
    return fname, hl, h[name]


def fetch(name, as_float=True):
    """Return the tensor `name` as a numpy array (BF16 -> exact float32)."""
    os.makedirs(TEN_DIR, exist_ok=True)
    fname, hl, info = tensor_info(name)
    path = os.path.join(TEN_DIR, name + ".bin")
    s, e = info["data_offsets"]
    if not os.path.exists(path) or os.path.getsize(path) != e - s:
        start = 8 + hl + s
        end = 8 + hl + e - 1
        tmp = path + ".part"
        _curl_range(BASE + fname, start, end, tmp)
        os.replace(tmp, path)
    raw = np.fromfile(path, dtype=np.uint8)
    dt = info["dtype"]
    shape = info["shape"]
    if dt == "BF16":
        a = raw.view(np.uint16).reshape(shape)
        return bf16_to_f32(a) if as_float else a
    if dt == "F32":
        return raw.view(np.float32).reshape(shape)
    if dt == "U8":
        return raw.reshape(shape)
    raise ValueError(dt)


def fetch_rows(name, rows):
    """Fetch selected rows of a 2-D BF16 tensor (e.g. embedding rows) without the full tensor."""
    fname, hl, info = tensor_info(name)
    assert info["dtype"] == "BF16" and len(info["shape"]) == 2
    ncol = info["shape"][1]
    s, _ = info["data_offsets"]
    out = []
    os.makedirs(TEN_DIR, exist_ok=True)
    for r in rows:
        path = os.path.join(TEN_DIR, f"{name}.row{r}.bin")
        if not os.path.exists(path):
            start = 8 + hl + s + r * ncol * 2
            _curl_range(BASE + fname, start, start + ncol * 2 - 1, path)
        out.append(bf16_to_f32(np.fromfile(path, dtype=np.uint16)))
    return np.stack(out)
