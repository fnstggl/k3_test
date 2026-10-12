#!/usr/bin/env python3
"""Fetch the public Kimi-K3 config and safetensors headers and build tensor manifests.

Only the JSON headers of the 96 safetensors shards are downloaded (HTTP range
requests), never the 1.56 TB of weights.  Outputs:

  data/k3/config.json                    (copied from the HF repo, pinned revision)
  data/k3/tensor_manifest_grouped.csv    (one row per tensor *type*, exact totals)
  data/k3/tensor_manifest_per_layer.csv  (one row per layer x tensor type)
  data/k3/manifest_totals.json           (bytes / element counts by dtype)

Usage:  python scripts/fetch_k3_manifest.py [--cache DIR]
"""
import argparse
import collections
import concurrent.futures as cf
import csv
import json
import os
import re
import struct
import subprocess
import sys

REPO = "moonshotai/Kimi-K3"
REV = "f831ab66814297da540d832a5235f8e904f29d06"  # revision inspected on 2026-10-12
BASE = f"https://huggingface.co/{REPO}/resolve/{REV}/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "k3")


def curl(url, rng=None, out=None):
    cmd = ["curl", "-sSL", "--fail", "--retry", "4"]
    if rng:
        cmd += ["-r", rng]
    if out:
        cmd += ["-o", out]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, check=True)
    return r.stdout


def fetch_header(fname, cache):
    path = os.path.join(cache, fname + ".json")
    if os.path.exists(path):
        return path
    n = struct.unpack("<Q", curl(BASE + fname, "0-7"))[0]
    raw = curl(BASE + fname, f"8-{8 + n - 1}")
    json.loads(raw)  # validate
    with open(path, "wb") as f:
        f.write(raw)
    return path


def generalize(name):
    g = re.sub(r"\.\d+\.", ".N.", name)
    return re.sub(r"\.\d+\.", ".N.", g)


def layer_of(name):
    m = re.search(r"layers\.(\d+)\.", name)
    return int(m.group(1)) if m else -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.path.join(ROOT, ".cache", "k3_headers"))
    args = ap.parse_args()
    os.makedirs(args.cache, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)

    cfg_path = os.path.join(OUT, "config.json")
    if not os.path.exists(cfg_path):
        curl(BASE + "config.json", out=cfg_path)
    idx_path = os.path.join(args.cache, "model.safetensors.index.json")
    if not os.path.exists(idx_path):
        curl(BASE + "model.safetensors.index.json", out=idx_path)
    idx = json.load(open(idx_path))
    files = sorted(set(idx["weight_map"].values()))
    with cf.ThreadPoolExecutor(8) as ex:
        paths = list(ex.map(lambda f: fetch_header(f, args.cache), files))

    grouped = collections.OrderedDict()
    per_layer = collections.OrderedDict()
    totals = collections.Counter()
    elems = collections.Counter()
    ntensors = 0
    for p in paths:
        h = json.load(open(p))
        for k, v in h.items():
            if k == "__metadata__":
                continue
            ntensors += 1
            s, e = v["data_offsets"]
            nb = e - s
            ne = 1
            for d in v["shape"]:
                ne *= d
            totals[v["dtype"]] += nb
            elems[v["dtype"]] += ne
            g = generalize(k)
            d = grouped.setdefault(g, {"count": 0, "bytes": 0, "elements": 0,
                                       "dtype": v["dtype"], "shape": v["shape"]})
            d["count"] += 1
            d["bytes"] += nb
            d["elements"] += ne
            key = (layer_of(k), g)
            d2 = per_layer.setdefault(key, {"count": 0, "bytes": 0, "elements": 0,
                                            "dtype": v["dtype"], "shape": v["shape"]})
            d2["count"] += 1
            d2["bytes"] += nb
            d2["elements"] += ne

    assert ntensors == len(idx["weight_map"]), (ntensors, len(idx["weight_map"]))
    assert sum(totals.values()) == idx["metadata"]["total_size"]

    with open(os.path.join(OUT, "tensor_manifest_grouped.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tensor_pattern", "count", "dtype", "shape_each", "elements_total", "bytes_total"])
        for g, d in grouped.items():
            w.writerow([g, d["count"], d["dtype"], "x".join(map(str, d["shape"])), d["elements"], d["bytes"]])
    with open(os.path.join(OUT, "tensor_manifest_per_layer.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["layer", "tensor_pattern", "count", "dtype", "shape_each", "elements_total", "bytes_total"])
        for (layer, g), d in sorted(per_layer.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            w.writerow([layer, g, d["count"], d["dtype"], "x".join(map(str, d["shape"])), d["elements"], d["bytes"]])
    json.dump({"repo": REPO, "revision": REV, "num_tensors": ntensors,
               "bytes_by_dtype": dict(totals), "elements_by_dtype": dict(elems),
               "total_bytes": sum(totals.values()),
               "index_total_size": idx["metadata"]["total_size"]},
              open(os.path.join(OUT, "manifest_totals.json"), "w"), indent=2)
    print(f"tensors={ntensors} total_bytes={sum(totals.values())} by_dtype={dict(totals)}")


if __name__ == "__main__":
    sys.exit(main())
