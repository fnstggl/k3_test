#!/usr/bin/env python3
"""Parse NeuroSim V1.4 VGG8 logs and compare against Table VII of the V1.4 user manual.

Usage: parse_baseline.py <logs/baseline dir> <out csv>
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
    'runtime_s': r'Total Run-time of NeuroSim: (\d+) seconds',
}


def pct(obs, exp):
    return '%.2f' % (100.0 * (obs - exp) / exp) if exp else ''


rows = []
for tag, t in TABLE7.items():
    path = os.path.join(logdir, tag + '.log')
    cfg = '%s %dnm on/off=%s ADC=%db parallelRead=%d 1b/cell 128x128 XY-bus' % t[:5]
    if not os.path.exists(path):
        stopped = [f for f in sorted(os.listdir(logdir)) if f.startswith(tag + '_') and ('STOPPED' in f or 'ABORTED' in f)]
        src_tag = 'sram22_' + tag.split('_')[1] if tag.startswith(('sram5', 'sram1')) else None
        if stopped:
            why = 'NOT COMPLETED: wrapper run stopped before finishing (CPU-time budget on the shared 4-core host); see logs/baseline/' + stopped[-1]
        elif src_tag and not os.path.exists(os.path.join(logdir, src_tag + '.log')):
            why = 'NOT RUN: needs the %s traces, whose wrapper run was not completed' % src_tag
        else:
            why = 'NOT RUN (no log)'
        for m, e in zip(['accuracy_pct', 'chip_area_mm2', 'tops', 'tops_per_w', 'tops_per_mm2'], t[5:]):
            rows.append(dict(config=cfg, metric=m, expected=e, expected_source=SRC, observed='', pct_diff='', notes=why))
        continue
    txt = open(path, errors='replace').read()
    got = {}
    for k, p in PATS.items():
        m = re.search(p, txt)
        if m:
            got[k] = (int(m.group(1)), int(m.group(2))) if k == 'accuracy' else float(m.group(1))
    if 'chip_area_um2' not in got:
        tail = txt.strip().splitlines()[-3:]
        for m, e in zip(['accuracy_pct', 'chip_area_mm2', 'tops', 'tops_per_w', 'tops_per_mm2'], t[5:]):
            rows.append(dict(config=cfg, metric=m, expected=e, expected_source=SRC, observed='', pct_diff='',
                             notes='RUN FAILED: ' + ' | '.join(tail)))
        continue
    reused = 'C++ re-run on the SRAM-22nm traces of the same parallelRead (wrapper never sees technode)' if tag.startswith(('sram5', 'sram1')) else ''
    acc = got.get('accuracy')
    acc_note = ('accuracy from only %d CIFAR-10 test image(s) on CPU (full 10k-image --inference 1 run is infeasible on this '
                '4-core CPU); NOT comparable to Table VII' % acc[1]) if acc else 'accuracy not printed'
    if reused:
        acc_note = 'not applicable: ' + reused
    obs_acc = 100.0 * acc[0] / acc[1] if acc else None
    rows.append(dict(config=cfg, metric='accuracy_pct', expected=t[5], expected_source=SRC,
                     observed='%.1f' % obs_acc if (obs_acc is not None and not reused) else '', pct_diff='', notes=acc_note))
    area_mm2 = got['chip_area_um2'] / 1e6
    for m, e, o in [('chip_area_mm2', t[6], area_mm2), ('tops', t[7], got.get('tops')),
                    ('tops_per_w', t[8], got.get('tops_per_w')), ('tops_per_mm2', t[9], got.get('tops_per_mm2'))]:
        note = reused
        if m == 'tops_per_mm2':
            note = (note + '; ' if note else '') + 'Table VII rounds TOPS/mm2 to 2 decimals'
        rows.append(dict(config=cfg, metric=m, expected=e, expected_source=SRC,
                         observed=('%.4g' % o) if o is not None else '', pct_diff=pct(o, e) if o is not None else '', notes=note))
    for k in ['clock_period_ns', 'pipeline_cycle_ns', 'read_dynamic_energy_pJ', 'leakage_energy_pJ', 'fps',
              'cim_array_area_um2', 'adc_area_um2', 'memory_utilization_pct', 'runtime_s']:
        if k in got:
            rows.append(dict(config=cfg, metric=k, expected='', expected_source='(not in Table VII)',
                             observed='%.6g' % got[k], pct_diff='', notes=reused))

with open(out, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['config', 'metric', 'expected', 'expected_source', 'observed', 'pct_diff', 'notes'])
    w.writeheader()
    w.writerows(rows)
print('wrote', out, len(rows), 'rows')
