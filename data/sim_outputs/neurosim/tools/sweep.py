#!/usr/bin/env python3
"""Per-subarray RRAM sweep with NeuroSim V1.4 (driven by tools/subarray_driver.cpp).

For every configuration: regenerate Param.cpp from the pristine git copy with set_param.py,
recompile Param.o, relink the driver against the unmodified NeuroSim objects, run it, save its
stdout to logs/sweep/<tag>.log and parse the RESULT_JSON line.

Outputs (in OUT_DIR):
  rram_subarray_sweep.csv                       - 22 nm (supported node), schema requested by caller
  rram_subarray_sweep_detailed.csv              - same rows, every field the driver reports
  rram_subarray_sweep_7nm_forced_UNSUPPORTED.csv - 7 nm with the main.cpp RRAM guard bypassed
  rram_subarray_sweep_colmux_sensitivity.csv    - 22 nm 1T1R flash, numColMuxed in {1,2,4,8,16}
"""
import argparse
import csv
import json
import os
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--build', required=True, help='driver build dir (contains src/ with NeuroSim objects + subarray_driver.o)')
ap.add_argument('--pristine', required=True, help='pristine Param.cpp from git')
ap.add_argument('--out', required=True)
ap.add_argument('--quick', action='store_true', help='tiny subset for testing')
ap.add_argument('--collect-only', action='store_true', help='do not run; rebuild the CSVs from existing logs/sweep/*.log')
args = ap.parse_args()

TOOLS = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(args.build, 'src')
LOGDIR = os.path.join(args.out, 'logs', 'sweep')
os.makedirs(LOGDIR, exist_ok=True)
CXX = ['g++', '-fopenmp', '-O3', '-std=c++0x', '-w']

SIZES = [128, 256, 512, 1024]
CELLBITS = [1, 2, 4]
ADCBITS = [4, 5, 6, 7, 8, 9, 10]
INPUT_BITS = 8
if args.quick:
    SIZES, CELLBITS, ADCBITS = [128], [1], [4, 5]

ARRAYS = {   # accesstype in Param.cpp
    '1T1R': (1, '1T1R pseudo-crossbar (accesstype=1, NeuroSim default; cell 4Fx12F)'),
    'XBAR': (4, '1S1R crossbar with ideal selector (accesstype=4; cell 2Fx2F)'),
}
ADCS = {
    'FLASH': ({'SARADC': 'false', 'currentMode': 'true'}, 'flash ADC = multilevel current-mode SA (MLSA/CSA, NeuroSim default)'),
    'SAR': ({'SARADC': 'true', 'currentMode': 'true'}, 'SAR ADC (SarADC.cpp)'),
}

configs = []
for arr in ['1T1R', 'XBAR']:
    for adc in ['FLASH', 'SAR']:
        if arr == 'XBAR' and adc == 'SAR':
            continue   # keep the sweep focused: crossbar only with the default flash ADC
        for n in SIZES:
            for cb in CELLBITS:
                for ab in ADCBITS:
                    configs.append(dict(node=22, arr=arr, adc=adc, n=n, cb=cb, ab=ab, force=False, colmux=8, sens=False))
for arr in ['1T1R', 'XBAR']:
    for n in SIZES:
        for cb in CELLBITS:
            for ab in ADCBITS:
                configs.append(dict(node=7, arr=arr, adc='FLASH', n=n, cb=cb, ab=ab, force=True, colmux=8, sens=False))

COLMUX = [1, 2, 4, 16] if not args.quick else [1]
for cm in COLMUX:   # numColMuxed=8 (default) rows are taken from the main sweep
    for n in SIZES:
        for cb in CELLBITS:
            for ab in [b for b in ADCBITS if b <= 8]:
                configs.append(dict(node=22, arr='1T1R', adc='FLASH', n=n, cb=cb, ab=ab, force=False, colmux=cm, sens=True))

objs = sorted(f for f in os.listdir(SRC) if f.endswith('.o') and f != 'Param.o')
results = []
for i, c in enumerate(configs):
    tag = 'n%d_%s_%s_%dx%d_cb%d_adc%d_in%d' % (c['node'], c['arr'], c['adc'], c['n'], c['n'], c['cb'], c['ab'], INPUT_BITS)
    if c['colmux'] != 8:
        tag += '_colmux%d' % c['colmux']
    knobs = ['memcelltype=2', 'accesstype=%d' % ARRAYS[c['arr']][0], 'technode=%d' % c['node'],
             'numRowSubArray=%d' % c['n'], 'numColSubArray=%d' % c['n'],
             'levelOutput=%d' % (2 ** c['ab']), 'cellBit=%d' % c['cb'], 'numColMuxed=%d' % c['colmux']]
    knobs += ['%s=%s' % kv for kv in ADCS[c['adc']][0].items()]
    log_path = os.path.join(LOGDIR, tag + '.log')
    if args.collect_only:
        if not os.path.exists(log_path):
            results.append((c, tag, None, ['no log']))
            continue
        txt = open(log_path).read()
        res = None
        for line in txt.splitlines():
            if line.startswith('RESULT_JSON '):
                res = json.loads(line[len('RESULT_JSON '):])
        results.append((c, tag, res, None if res else txt.strip().splitlines()[-2:]))
        continue
    with open(log_path, 'w') as log:
        log.write('# config: %s\n# Param.cpp knobs: %s\n# driver args: --synapse-bit 8 --input-bit %d --p-input 0.5 --seed 12345%s\n'
                  % (json.dumps(c), ' '.join(knobs), INPUT_BITS, ' --force-unsupported' if c['force'] else ''))
        log.flush()
        sp = subprocess.run([sys.executable, os.path.join(TOOLS, 'set_param.py'), args.pristine,
                             os.path.join(SRC, 'Param.cpp')] + knobs, stdout=log, stderr=subprocess.STDOUT)
        if sp.returncode:
            sys.exit('set_param failed for ' + tag)
        subprocess.run(CXX + ['-c', 'Param.cpp', '-o', 'Param.o'], cwd=SRC, check=True)
        exe = os.path.join(args.build, 'driver_current')
        subprocess.run(CXX + objs + ['Param.o', '-o', exe], cwd=SRC, check=True)
        cmd = [exe, '--synapse-bit', '8', '--input-bit', str(INPUT_BITS), '--p-input', '0.5', '--seed', '12345']
        if c['force']:
            cmd.append('--force-unsupported')
        log.write('# command: %s\n' % ' '.join(cmd))
        log.flush()
        rp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        log.write(rp.stdout)
        log.write('# exit code: %d\n' % rp.returncode)
    res = None
    for line in rp.stdout.splitlines():
        if line.startswith('RESULT_JSON '):
            res = json.loads(line[len('RESULT_JSON '):])
    if rp.returncode or res is None:
        print('[sweep] FAILED %s (exit %d) -> see %s' % (tag, rp.returncode, log_path))
        results.append((c, tag, None, rp.stdout.strip().splitlines()[-1:] if rp.stdout else ['']))
        continue
    results.append((c, tag, res, None))
    if i % 20 == 0:
        print('[sweep] %d/%d %s  lat=%.3f ns  E=%.3f pJ' % (i + 1, len(configs), tag, res['latency_ns'], res['energy_pJ']), flush=True)


def macs(r):
    return r['rows'] * (r['cols'] // r['numColPerSynapse'])


def derived(r):
    m = macs(r)
    area_mm2 = r['subarrayArea_um2'] * 1e-6
    tops = 2.0 * m / (r['latency_ns'] * 1e-9) / 1e12
    return {'weights_per_subarray': m, 'macs_per_mvm': m, 'energy_fJ_per_mac': r['energy_pJ'] * 1e3 / m,
            'tops_per_w_subarray': 2.0 * m / r['energy_pJ'], 'tops_subarray': tops, 'tops_per_mm2_subarray': tops / area_mm2,
            'weight_density_Mb_per_mm2': m * 8 / 1e6 / area_mm2}


def notes_for(c, r):
    parts = [
        'array=' + c['arr'], 'adc=' + c['adc'],
        'numColMuxed=%d' % r['numColMuxed'], 'numADC=%d' % r['numADC'],
        'numRowParallel=%d(full)' % r['numRowParallel'], 'synapseBit=8(%d cells/weight)' % r['numColPerSynapse'],
        'Ron=%.0f' % r['Ron'], 'Roff=%.0f' % r['Roff'], 'Vread=%g' % r['readVoltage'],
        'sensing_cycle_ns=%.4g' % r['sensingCycle_ns'], 'latency=%d cycles x sensing cycle (synchronous; shift-add hidden)' % round(r['latency_cycles']),
        'energy=subarray only (excl. PE buffers/adder tree/interconnect)', 'ADC conv/MVM=%d' % r['adcConversions'],
        'inputs=Bernoulli(0.5) bits; weights=uniform random 8b',
        'MACs/MVM=%d (%d rows x %d 8b weights)' % (macs(r), r['rows'], r['cols'] // r['numColPerSynapse']),
        'fJ/MAC=%.4g' % (r['energy_pJ'] * 1e3 / macs(r)),
    ]
    if r['numColMuxed'] == 2:
        parts.insert(0, 'MODEL ARTIFACT: numColMuxed=2 -> 1-address-bit mux decoder; RowDecoder.cpp:73-81 then instantiates no NAND/NOR gates (0 area) and reports a ~12 ns delay that sets the clock; do not use')
    elif r['muxdelay_ns'] > (r['adcLatencyLUT_ns'] if c['adc'] == 'FLASH' else r['adcBits'] + 1.0):
        parts.insert(0, 'CAUTION: sensing cycle limited by column-mux decoder delay (%.3g ns > ADC %.3g ns); mux/decoder sizing (Param.cpp:151-160 sizingfactor_MUX) appears tuned for the default numColMuxed=8'
                     % (r['muxdelay_ns'], r['adcLatencyLUT_ns'] if c['adc'] == 'FLASH' else r['adcBits'] + 1.0))
    if c['adc'] == 'FLASH' and r['adcBits'] >= 9:
        parts.insert(0, 'CAUTION: >=9b flash ADC uses MultilevelSenseAmp.cpp ColumnLatency_Table fits far outside the default reference-resistance range (extrapolated)')
    if c['adc'] == 'FLASH':
        parts.append('encoder dyn. energy=0 by design (MultilevelSAEncoder.cpp:219-220)')
    if c['force']:
        parts.insert(0, 'UNSUPPORTED NODE: NeuroSim V1.4 main.cpp:86-90 rejects RRAM at <=14nm; guard bypassed (--force-unsupported)')
    return '; '.join(parts)


main_cols = ['tech_node_nm', 'rows', 'cols', 'cell_bits', 'adc_bits', 'input_bits', 'latency_ns_per_mvm', 'energy_pJ_per_mvm',
             'adc_energy_pJ_per_conversion', 'adc_area_um2', 'subarray_area_um2', 'area_breakdown_json', 'leakage_uW', 'notes']


def main_row(c, r):
    return {
        'tech_node_nm': c['node'], 'rows': r['rows'], 'cols': r['cols'], 'cell_bits': r['cellBit'], 'adc_bits': int(r['adcBits']),
        'input_bits': r['inputBits'], 'latency_ns_per_mvm': '%.6g' % r['latency_ns'], 'energy_pJ_per_mvm': '%.6g' % r['energy_pJ'],
        'adc_energy_pJ_per_conversion': '%.6g' % r['adcEnergyPerConv_pJ'], 'adc_area_um2': '%.6g' % r['adcAreaPerADC_um2'],
        'subarray_area_um2': '%.6g' % r['subarrayArea_um2'],
        'area_breakdown_json': json.dumps({k: round(v, 4) for k, v in r['area_breakdown_um2'].items()}, separators=(',', ':')),
        'leakage_uW': '%.6g' % r['leakage_uW'], 'notes': notes_for(c, r),
    }


def flat(prefix, d, out):
    for k, v in d.items():
        if isinstance(v, dict):
            flat(prefix + k + '.', v, out)
        else:
            out[prefix + k] = v
    return out


def write(path, rows_, cols_):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols_)
        w.writeheader()
        for row in rows_:
            w.writerow(row)
    print('[sweep] wrote %s (%d rows)' % (path, len(rows_)))


ok22 = [(c, t, r) for c, t, r, e in results if r is not None and not c['force'] and not c['sens']]
okcm = [(c, t, r) for c, t, r, e in results if r is not None and (c['sens'] or (c['node'] == 22 and c['arr'] == '1T1R' and c['adc'] == 'FLASH' and c['ab'] <= 8))]
okcm.sort(key=lambda x: (x[0]['n'], x[0]['cb'], x[0]['ab'], x[0]['colmux']))
ok7 = [(c, t, r) for c, t, r, e in results if r is not None and c['force']]
failed = [(c, t, e) for c, t, r, e in results if r is None]
write(os.path.join(args.out, 'rram_subarray_sweep.csv'), [main_row(c, r) for c, t, r in ok22], main_cols)
write(os.path.join(args.out, 'rram_subarray_sweep_7nm_forced_UNSUPPORTED.csv'), [main_row(c, r) for c, t, r in ok7], main_cols)
write(os.path.join(args.out, 'rram_subarray_sweep_colmux_sensitivity.csv'),
      [dict(main_row(c, r), numColMuxed=r['numColMuxed']) for c, t, r in okcm], main_cols[:6] + ['numColMuxed'] + main_cols[6:])
det = []
for c, t, r in ok22 + ok7 + [x for x in okcm if x[0]['sens']]:
    d = {'tag': t, 'array': c['arr'], 'adc_type': c['adc'], 'forced_unsupported_node': int(c['force']), 'colmux_sensitivity_only': int(c['sens'])}
    flat('', r, d)
    d.update(derived(r))
    det.append(d)
det_cols = []
for d in det:
    for k in d:
        if k not in det_cols:
            det_cols.append(k)
write(os.path.join(args.out, 'rram_subarray_sweep_detailed.csv'), det, det_cols)
print('[sweep] %d configs, %d ok, %d failed' % (len(results), len(results) - len(failed), len(failed)))
for c, t, e in failed:
    print('[sweep]   FAILED', t, e)
