#!/usr/bin/env python3
"""Parse NeuroSim V1.4 VGG8 logs and compare against Table VII of the V1.4 user manual.

Usage: parse_baseline.py <logs/baseline dir> <out csv>

For every Table VII row two runs may exist:
  <tag>.log       wrapper --inference 1 (hardware-aware forward pass = the manual's flow; traces of image #1)
  <tag>_inf0.log  wrapper --inference 0 (ideal 8-bit forward; same trace files/format, same C++ binary)
"""
import csv
import os
import re
import sys

logdir, out = sys.argv[1], sys.argv[2]
SRC = ('NeuroSim V1.4 user manual "User Manual of DNN simulator_V1.4_v3_updated_1229.pdf", '
       'Sec. 11 Table VII "Hardware Estimation Examples" (p.32; table dated 9/27/23)')
# Table VII rows: (memory, node, on/off, ADC bits, parallelRead) -> accuracy %, area mm2, TOPS, TOPS/W, TOPS/mm2
TABLE7 = {
    'rram22_pr32': ('RRAM', 22, '17', 4, 32, 71, 381.90, 6.25, 11.25, 0.01),
    'rram22_pr64': ('RRAM', 22, '17', 4, 64, 43, 378.06, 8.16, 19.88, 0.02),
    'sram22_pr32': ('SRAM', 22, 'inf', 4, 32, 77, 85.97, 6.06, 8.76, 0.07),
    'sram22_pr64': ('SRAM', 22, 'inf', 4, 64, 59, 84.39, 8.01, 17.13, 0.09),
    'sram5_pr32': ('SRAM', 5, 'inf', 4, 32, 77, 14.64, 11.48, 32.43, 0.78),
    'sram5_pr64': ('SRAM', 5, 'inf', 4, 64, 59, 14.33, 11.96, 54.41, 0.83),
    'sram1_pr32': ('SRAM', 1, 'inf', 4, 32, 77, 8.34, 12.27, 65.08, 1.47),
    'sram1_pr64': ('SRAM', 1, 'inf', 4, 64, 59, 8.27, 13.08, 105.97, 1.58),
}
MAIN = ['accuracy_pct', 'chip_area_mm2', 'tops', 'tops_per_w', 'tops_per_mm2']
PATS = {
    'chip_area_um2': r'ChipArea : ([0-9.eE+-]+)um\^2',
    'cim_array_area_um2': r'Chip total CIM array : ([0-9.eE+-]+)um\^2',
    'adc_area_um2': r'Total ADC \(or S/As and precharger for SRAM\) Area on chip : ([0-9.eE+-]+)um\^2',
    'clock_period_ns': r'Chip clock period is: ([0-9.eE+-]+)ns',
    'pipeline_cycle_ns': r'Chip pipeline-system-clock-cycle \(per image\) is: ([0-9.eE+-]+)ns',
    'read_dynamic_energy_pJ': r'Chip pipeline-system readDynamicEnergy \(per image\) is: ([0-9.eE+-]+)pJ',
    'leakage_energy_pJ': r'Chip pipeline-system leakage Energy \(per image\) is: ([0-9.eE+-]+)pJ',
    'tops_per_w': r'Energy Efficiency TOPS/W \(Pipelined Process\): ([0-9.eE+-]+)',
    'tops': r'Throughput TOPS \(Pipelined Process\): ([0-9.eE+-]+)',
    'fps': r'Throughput FPS \(Pipelined Process\): ([0-9.eE+-]+)',
    'tops_per_mm2': r'Compute efficiency TOPS/mm\^2 \(Pipelined Process\): ([0-9.eE+-]+)',
    'memory_utilization_pct': r'Memory Utilization of Whole Chip: ([0-9.eE+-]+) %',
    'accuracy': r'Accuracy: (\d+)/(\d+) \(',
    'neurosim_runtime_s': r'Total Run-time of NeuroSim: (\d+) seconds',
    'wall_seconds': r'# exit=\d+ wall_seconds=(\d+)',
}
EXTRA = ['clock_period_ns', 'pipeline_cycle_ns', 'read_dynamic_energy_pJ', 'leakage_energy_pJ', 'fps',
         'cim_array_area_um2', 'adc_area_um2', 'memory_utilization_pct', 'neurosim_runtime_s', 'wall_seconds']
VARIANTS = [('', 'C++ @HEAD 8a88abf; wrapper --inference 1 traces (HW-aware forward = manual flow; test image #1)'),
            ('_inf0', 'C++ @HEAD 8a88abf; wrapper --inference 0 traces (ideal 8-bit forward; test image #1)'),
            ('_code6a6073d', 'C++ @6a6073d (original 2024-10-04 V1.4 upload); wrapper --inference 1 traces'),
            ('_inf0_code6a6073d', 'C++ @6a6073d (original 2024-10-04 V1.4 upload); wrapper --inference 0 traces'),
            ('_hyb', 'C++ @HEAD 8a88abf; HYBRID traces: --inference 1 for the 6 conv layers (98.6% of MACs), --inference 0 for the 2 FC layers'),
            ('_hyb_code6a6073d', 'C++ @6a6073d (original upload); HYBRID traces: --inference 1 conv layers + --inference 0 FC layers')]
PARTNER = {'': '_inf0', '_inf0': '', '_code6a6073d': '_inf0_code6a6073d', '_inf0_code6a6073d': '_code6a6073d',
           '_hyb': '_inf0', '_hyb_code6a6073d': '_inf0_code6a6073d'}


def parse(path):
    txt = open(path, errors='replace').read()
    got = {}
    for k, p in PATS.items():
        m = re.search(p, txt)
        if m:
            got[k] = (int(m.group(1)), int(m.group(2))) if k == 'accuracy' else float(m.group(1))
    if 'chip_area_um2' in got:
        got['chip_area_mm2'] = got['chip_area_um2'] / 1e6
    return got, txt


def pct(obs, exp):
    return '%.2f' % (100.0 * (obs - exp) / exp) if exp else ''


parsed = {}
for tag in TABLE7:
    for suf, _ in VARIANTS:
        p = os.path.join(logdir, tag + suf + '.log')
        if os.path.exists(p):
            parsed[tag + suf] = parse(p)

rows = []
for tag, t in TABLE7.items():
    cfg = '%s %dnm on/off=%s ADC=%db parallelRead=%d 1b/cell 128x128 XY-bus' % t[:5]
    exp = dict(zip(MAIN, t[5:]))
    for suf, src in VARIANTS:
        key = tag + suf
        reuse = ''
        if tag.startswith(('sram5', 'sram1')):
            reuse = 'C++ re-run on the sram22_pr%s%s traces (the wrapper never sees technode)' % (tag.split('pr')[1], suf.replace('_code6a6073d', ''))
        if key not in parsed and 'hyb' in suf:
            continue
        if key not in parsed:
            stopped = [f for f in sorted(os.listdir(logdir)) if f.startswith(key + '_') and ('STOPPED' in f or 'ABORTED' in f)]
            if stopped:
                why = ('NOT COMPLETED: run stopped before finishing (CPU-time budget on the shared 4-core host); see '
                       'logs/baseline/' + stopped[-1])
            elif 'inf0' not in suf:
                why = ('NOT RUN with --inference 1 traces (one image needs 1-3 h of CPU per config here); see the '
                       '--inference 0 rows for this config')
            else:
                why = 'NOT RUN (no log)'
            for m in MAIN:
                rows.append(dict(config=cfg, trace_source=src, metric=m, expected=exp[m], expected_source=SRC,
                                 observed='', pct_diff='', notes=why))
            continue
        got, txt = parsed[key]
        if 'chip_area_um2' not in got:
            tail = ' | '.join(txt.strip().splitlines()[-3:])
            for m in MAIN:
                rows.append(dict(config=cfg, trace_source=src, metric=m, expected=exp[m], expected_source=SRC,
                                 observed='', pct_diff='', notes='RUN DID NOT FINISH / FAILED: ' + tail))
            continue
        other = parsed.get(tag + PARTNER[suf], ({}, ''))[0]
        acc = got.get('accuracy')
        for m in MAIN:
            note = reuse
            if m == 'accuracy_pct':
                if 'hyb' in suf:
                    rows.append(dict(config=cfg, trace_source=src, metric=m, expected=exp[m], expected_source=SRC,
                                     observed='', pct_diff='', notes='not applicable (C++-only re-run on hybrid traces)'))
                    continue
                if reuse or not acc:
                    obs = None
                    note = 'not applicable: ' + reuse if reuse else 'accuracy not printed'
                else:
                    obs = 100.0 * acc[0] / acc[1]
                    note = ('top-1 on only %d test image (full 10k-image --inference 1 run is infeasible on this CPU); '
                            'NOT comparable to Table VII' % acc[1])
                    if 'inf0' in suf:
                        note = 'software accuracy (no HW effects) on %d image; NOT comparable' % acc[1]
            else:
                obs = got.get(m)
                if m == 'tops_per_mm2':
                    note = (note + '; ' if note else '') + 'Table VII rounds TOPS/mm2 to 2 decimals'
                if obs is not None and other.get(m) is not None and 'inf0' in suf:
                    note = (note + '; ' if note else '') + 'vs --inference 1 run of the same config: %+.3f %%' % (100.0 * (obs - other[m]) / other[m])
                if obs is not None and other.get(m) is not None and 'hyb' in suf:
                    note = (note + '; ' if note else '') + 'vs the all---inference-0-trace run of the same code: %+.3f %%' % (100.0 * (obs - other[m]) / other[m])
            rows.append(dict(config=cfg, trace_source=src, metric=m, expected=exp[m], expected_source=SRC,
                             observed=('%.4g' % obs) if obs is not None else '',
                             pct_diff=pct(obs, exp[m]) if (obs is not None and m != 'accuracy_pct') else '', notes=note))
        for k in EXTRA:
            if k in got:
                rows.append(dict(config=cfg, trace_source=src, metric=k, expected='', expected_source='(not in Table VII)',
                                 observed='%.6g' % got[k], pct_diff='', notes=reuse))

with open(out, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['config', 'trace_source', 'metric', 'expected', 'expected_source', 'observed', 'pct_diff', 'notes'])
    w.writeheader()
    w.writerows(rows)
print('wrote', out, len(rows), 'rows')
