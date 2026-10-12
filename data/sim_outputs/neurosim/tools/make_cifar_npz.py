#!/usr/bin/env python3
"""Convert the HuggingFace uoft-cs/cifar10 test parquet into a uint8 npz used by run_wrapper.py.

Usage: python -I make_cifar_npz.py <test-00000-of-00001.parquet> <out.npz>
Output: images (10000,32,32,3) uint8 RGB, labels (10000,) int64, canonical CIFAR-10 test order
(labels[:10] == 3 8 8 0 6 6 1 6 3 1).
"""
import io
import sys

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
d = pq.read_table(src).to_pydict()
imgs = np.stack([np.array(Image.open(io.BytesIO(x['bytes'])).convert('RGB')) for x in d['img']])
labels = np.array(d['label'], dtype=np.int64)
assert imgs.shape == (10000, 32, 32, 3) and list(labels[:10]) == [3, 8, 8, 0, 6, 6, 1, 6, 3, 1]
np.savez_compressed(dst, images=imgs, labels=labels)
print('wrote', dst, imgs.shape, np.bincount(labels))
