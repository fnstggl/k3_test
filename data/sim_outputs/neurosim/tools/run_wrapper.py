#!/usr/bin/env python3
"""Run NeuroSim V1.4's unmodified inference.py on CPU with a local CIFAR-10 test subset.

Why this exists
  * inference.py calls models.dataset.get_cifar10(), which downloads CIFAR-10 via torchvision
    into /tmp/public_dataset.  The original toronto.edu host was ~50 KB/s from this container,
    so we use the HuggingFace mirror uoft-cs/cifar10 (test split parquet, sha256
    841389e6f2d64f28bf17310e430aebac20ec3ba611a3c5e231dc93c645ce84de), pre-converted to
    cifar10_test_uint8.npz (same 10,000 images, same canonical order; labels[:10] =
    3 8 8 0 6 6 1 6 3 1).
  * The --inference 1 forward pass performs thousands of full-size masked convolutions per
    layer; on a 4-core CPU only a handful of test images is affordable.  NeuroSim's hardware
    trace hook only records the FIRST image of the FIRST batch, so the C++ hardware estimate
    is unaffected by --n_images; only the reported accuracy is (it becomes a tiny-sample
    estimate).

This runner monkey-patches models.dataset.get_cifar10 to return a loader over the first
--n_images test images with the identical transforms (ToTensor + Normalize(0.5,0.5,0.5)),
defaults torch.load(map_location='cpu') (the shipped VGG8.pth holds CUDA tensors), then
executes inference.py unchanged via runpy.  Must be run with cwd = Inference_pytorch.
"""
import argparse
import os
import runpy
import sys

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument('--n_images', type=int, default=1)
ap.add_argument('--npz', default='/home/user/ext/datasets/hf_cifar10/cifar10_test_uint8.npz')
ap.add_argument('--threads', type=int, default=4)
known, passthrough = ap.parse_known_args()

wrapper_dir = os.getcwd()
assert os.path.isfile(os.path.join(wrapper_dir, 'inference.py')), 'run from Inference_pytorch/'
sys.path.insert(0, wrapper_dir)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch.utils.data import DataLoader, Dataset  # noqa: E402
from torchvision import transforms  # noqa: E402

torch.set_num_threads(known.threads)

# The shipped log/VGG8.pth was saved from CUDA tensors; models/VGG.py calls torch.load(path)
# without map_location, which fails on a CPU-only machine.  Default map_location to CPU.
_orig_torch_load = torch.load


def _cpu_torch_load(*a, **kw):
    kw.setdefault('map_location', torch.device('cpu'))
    return _orig_torch_load(*a, **kw)


torch.load = _cpu_torch_load

from models import dataset as ns_dataset  # noqa: E402  (same module object inference.py imports)


class NpzCifar10Test(Dataset):
    def __init__(self, path, n, transform):
        z = np.load(path, allow_pickle=False)
        self.images = z['images'][:n]
        self.labels = z['labels'][:n]
        self.transform = transform

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        from PIL import Image
        img = Image.fromarray(self.images[i])
        return self.transform(img), int(self.labels[i])


def get_cifar10_local(batch_size, data_root=None, train=True, val=True, **kwargs):
    tf = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
    ])
    test_ds = NpzCifar10Test(known.npz, known.n_images, tf)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=0)
    print('[run_wrapper] local CIFAR-10 test subset: %d images, batch_size=%d' % (len(test_ds), batch_size))
    # inference.py unpacks (train_loader, test_loader) but never uses the train loader.
    return (None, test_loader) if (train and val) else test_loader


ns_dataset.get_cifar10 = get_cifar10_local

sys.argv = ['inference.py'] + passthrough
runpy.run_path(os.path.join(wrapper_dir, 'inference.py'), run_name='__main__')
