/*
 * subarray_driver.cpp -- single-subarray, single-MVM (batch 1) PPA driver for DNN+NeuroSim V1.4.
 *
 * Links against the UNMODIFIED NeuroSim V1.4 objects (everything except main.o).  All hardware
 * knobs come from Param.cpp, which the sweep script regenerates per configuration with
 * tools/set_param.py (memcelltype, accesstype, technode, numRowSubArray, numColSubArray,
 * levelOutput, cellBit, SARADC, ...), exactly as the V1.4 manual instructs users to do.
 *
 * What it does (mirrors main.cpp + ProcessingUnit.cpp, see README for line references):
 *   1. Applies the same run-time overrides main.cpp applies from argv (synapseBit, numBitInput,
 *      numRowParallel), the same operation-mode / numColPerSynapse logic, and the same
 *      "RRAM-CIM is not supported beyond 22 nm" guard (can be bypassed with --force-unsupported).
 *   2. ProcessingUnitInitialize(subArray, ..., 1,1,1,1): a PE that contains exactly one subarray.
 *   3. Builds a rows x cols conductance matrix from uniform-random 8-bit weights using the same
 *      bit-slicing / conductance mapping as Chip.cpp::LoadInWeightData, and one random 8-bit
 *      input vector stored as numBitInput bit-planes (Bernoulli(p_input) per bit).
 *   4. Synchronous mode (Param.cpp default): pass 1 computes the sensing-limited clock period
 *      via ProcessingUnitCalculatePerformance(..., CalculateclkFreq=true); clkFreq is then
 *      capped exactly as main.cpp does; pass 2 evaluates each input bit-plane with
 *      SubArray::CalculateLatency/CalculatePower (same loop body as ProcessingUnit.cpp) and
 *      sums the bit-planes = one bit-serial MVM.  Latencies are cycles * clkPeriod (main.cpp).
 *   5. Also calls ProcessingUnitCalculatePerformance(..., false) for the 1-subarray PE totals
 *      (adds PE input/output DFF buffers, PE adder tree, PE buses).
 *   6. Prints a human-readable report and one machine-readable line starting "RESULT_JSON ".
 *
 * Usage: subarray_driver [--synapse-bit N] [--input-bit N] [--p-input P] [--seed S]
 *                        [--force-unsupported] [--dump-traces PREFIX]
 *   --dump-traces writes PREFIX_weight.csv / PREFIX_input.csv in the PyTorch-wrapper trace format so the
 *   stock ./main can be run on identical data (used for the driver-vs-main cross-check).
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <random>
#include "constant.h"
#include "formula.h"
#include "Param.h"
#include "Tile.h"
#include "Chip.h"
#include "ProcessingUnit.h"
#include "SubArray.h"
#include "Definition.h"   // defines the globals param, gen, inputParameter, tech, cell (include once)

using namespace std;

static string jnum(double v) {
	if (std::isnan(v) || std::isinf(v)) return "null";
	char buf[64];
	snprintf(buf, sizeof(buf), "%.9g", v);
	return string(buf);
}

int main(int argc, char *argv[]) {
	int synapseBit = 8, inputBit = 8;
	double pInput = 0.5;
	unsigned seed = 12345;
	bool forceUnsupported = false;
	string dumpPrefix;
	for (int i = 1; i < argc; i++) {
		string a = argv[i];
		if (a == "--dump-traces" && i + 1 < argc) { dumpPrefix = argv[++i]; continue; }
		if (a == "--synapse-bit" && i + 1 < argc) synapseBit = atoi(argv[++i]);
		else if (a == "--input-bit" && i + 1 < argc) inputBit = atoi(argv[++i]);
		else if (a == "--p-input" && i + 1 < argc) pInput = atof(argv[++i]);
		else if (a == "--seed" && i + 1 < argc) seed = (unsigned)strtoul(argv[++i], NULL, 10);
		else if (a == "--force-unsupported") forceUnsupported = true;
		else { cerr << "unknown arg " << a << endl; return 2; }
	}
	gen.seed(0);

	/* ---- run-time overrides that main.cpp:73-76 applies from argv ---- */
	param->synapseBit = synapseBit;
	param->numBitInput = inputBit;
	// numRowSubArray/numColSubArray/levelOutput/cellBit come from Param.cpp (baked per config).
	param->numRowParallel = param->numRowSubArray;   // full parallel read (all rows on)

	if (param->cellBit > param->synapseBit) {      // main.cpp:79-82
		cout << "ERROR!: Memory precision is even higher than synapse precision" << endl;
		param->cellBit = param->synapseBit;
	}
	bool unsupportedNode = (param->memcelltype == 2 && param->technode <= 14);  // main.cpp:86-90
	if (unsupportedNode && !forceUnsupported) {
		cout << "ERROR!: RRAM-CIM is not supported beyond 22 nm!" << endl;
		return 3;
	}
	if (unsupportedNode) {
		cout << "WARNING: --force-unsupported: bypassing main.cpp:86-90 guard (RRAM at <=14 nm is NOT supported by NeuroSim V1.4)" << endl;
	}

	/* ---- operation mode & synapse mapping, main.cpp:119-154 ---- */
	param->conventionalParallel = param->conventionalSequential = 0;
	param->BNNparallelMode = param->BNNsequentialMode = 0;
	param->XNORsequentialMode = param->XNORparallelMode = 0;
	switch (param->operationmode) {
		case 6: param->XNORparallelMode = 1; break;
		case 5: param->XNORsequentialMode = 1; break;
		case 4: param->BNNparallelMode = 1; break;
		case 3: param->BNNsequentialMode = 1; break;
		case 2: param->conventionalParallel = 1; break;
		case 1: param->conventionalSequential = 1; break;
		default: return 4;
	}
	param->numRowPerSynapse = (param->XNORparallelMode || param->XNORsequentialMode) ? 2 : 1;
	if (param->BNNparallelMode) param->numColPerSynapse = 2;
	else if (param->XNORparallelMode || param->XNORsequentialMode || param->BNNsequentialMode) param->numColPerSynapse = 1;
	else param->numColPerSynapse = ceil((double)param->synapseBit / (double)param->cellBit);

	const int rows = param->numRowSubArray;
	const int cols = param->numColSubArray;
	if (rows != cols) {
		// ProcessingUnit.cpp sets subArray->numCol = param->numRowSubArray, i.e. NeuroSim assumes square subarrays.
		cout << "ERROR: NeuroSim V1.4 ProcessingUnitInitialize assumes square subarrays" << endl;
		return 5;
	}

	/* ---- PE with exactly one subarray (CM path), ProcessingUnit.cpp:71-251 ---- */
	SubArray *subArray = NULL;
	ProcessingUnitInitialize(subArray, inputParameter, tech, cell, 1, 1, 1, 1);
	double peH = 0, peW = 0, peBufArea = 0;
	vector<double> peArea = ProcessingUnitCalculateArea(subArray, 1, 1, false, &peH, &peW, &peBufArea);
	// peArea = {PE area, ADC, Accum(+adder tree), Other(+PE in/out buffers), Array}

	/* ---- synthetic weight & input traces ---- */
	std::mt19937 rng(seed);
	const int cellRange = (int)pow(2, param->cellBit);
	const int nColPerSyn = param->numColPerSynapse;
	const int nWeightsPerRow = cols / nColPerSyn;
	std::uniform_int_distribution<int> wdist(0, (int)pow(2, param->synapseBit) - 1);
	vector<vector<double> > memory(rows, vector<double>(cols, param->minConductance));
	double sumCellLevel = 0; long nCells = 0;
	for (int r = 0; r < rows; r++) {
		for (int w = 0; w < nWeightsPerRow; w++) {
			int value = wdist(rng);
			vector<double> syn;      // MSB first, as Chip.cpp::LoadInWeightData
			for (int z = 0; z < nColPerSyn; z++) { syn.insert(syn.begin(), (double)(value % cellRange)); value /= cellRange; }
			for (int u = 0; u < nColPerSyn; u++) {
				memory[r][w * nColPerSyn + u] = syn[u] / (cellRange - 1) * (param->maxConductance - param->minConductance) + param->minConductance;
				sumCellLevel += syn[u]; nCells++;
			}
		}
	}
	std::bernoulli_distribution bdist(pInput);
	vector<vector<double> > inputVec(rows, vector<double>(inputBit, 0));
	long onesTotal = 0;
	for (int r = 0; r < rows; r++) for (int k = 0; k < inputBit; k++) { inputVec[r][k] = bdist(rng) ? 1 : 0; onesTotal += (long)inputVec[r][k]; }
	if (!dumpPrefix.empty()) {
		// Re-generate the same integer weights (same seed) and write them in the wrapper's trace format:
		// weight CSV = rows x (cols/numColPerSynapse) floats f with Chip.cpp mapping round(128*(f+1)) == value (8-bit),
		// input CSV  = rows x numBitInput bits.  Lets the stock ./main consume exactly the same traces.
		std::mt19937 rng2(seed);
		std::uniform_int_distribution<int> wdist2(0, (int)pow(2, param->synapseBit) - 1);
		FILE *fw = fopen((dumpPrefix + "_weight.csv").c_str(), "w");
		double half = pow(2, param->synapseBit) / 2.0;
		for (int r = 0; r < rows; r++) {
			for (int w = 0; w < nWeightsPerRow; w++) fprintf(fw, "%s%.7f", w ? "," : "", wdist2(rng2) / half - 1.0);
			fprintf(fw, "\n");
		}
		fclose(fw);
		FILE *fi = fopen((dumpPrefix + "_input.csv").c_str(), "w");
		for (int r = 0; r < rows; r++) {
			for (int k = 0; k < inputBit; k++) fprintf(fi, "%s%d", k ? "," : "", (int)inputVec[r][k]);
			fprintf(fi, "\n");
		}
		fclose(fi);
	}

	/* ---- pass 1: sensing-limited clock (synchronous mode), main.cpp:289-306 ---- */
	double clkPeriod = 0;
	{
		double a, b, c, d, e, f, g, h, i1, j, k1, l, m, n, o;
		ProcessingUnitCalculatePerformance(subArray, memory, memory, inputVec, 1, 1, 1, 1, rows, cols, inputBit, cell, false,
			&a, &b, &c, &d, &e, &f, &g, &h, &i1, &j, &k1, &l, &m, &n, true, &clkPeriod);
	}
	double clkFreqUsed = param->clkFreq;
	double sensingCycle_s = clkPeriod;     // = (max(row-switch, mux) + ADC + encoder) * beta
	double rowdelay_s = param->rowdelay, muxdelay_s = param->muxdelay, adcLatencyLUT_s = param->ADClatency;
	if (param->synchronous) {
		if (param->clkFreq > 1 / clkPeriod) param->clkFreq = 1 / clkPeriod;
		clkFreqUsed = param->clkFreq;
	}
	const double cyc2s = param->synchronous ? clkPeriod : 1.0;   // main.cpp multiplies cycle counts by clkPeriod

	/* ---- pass 2: subarray-only, one bit-plane at a time (ProcessingUnit.cpp:497-534 loop body) ---- */
	subArray->clkFreq = param->clkFreq;
	double latCyc = 0, latADC = 0, latAccum = 0, latOther = 0;
	double eTot = 0, eADCcat = 0, eAccumCat = 0, eOtherCat = 0;
	double eArray = 0, eMLSA = 0, eEnc = 0, eSAR = 0, eMux = 0, eMuxDec = 0, eWLsw = 0, eSLsw = 0;
	double eShiftIn = 0, eShiftW = 0, eAdder = 0, eDff = 0;
	double leakage = 0, actSum = 0;
	for (int k = 0; k < inputBit; k++) {
		double activityRowRead = 0;
		vector<double> input = GetInputVector(inputVec, k, &activityRowRead);
		subArray->activityRowRead = activityRowRead;
		actSum += activityRowRead;
		if (param->parallelRead) subArray->levelOutput = param->levelOutput; else subArray->levelOutput = cellRange;
		vector<double> columnResistance = GetColumnResistance(input, memory, cell, param->parallelRead, subArray->resCellAccess);
		subArray->CalculateLatency(1e20, columnResistance, false);
		subArray->CalculatePower(columnResistance);
		latCyc += subArray->readLatency; latADC += subArray->readLatencyADC; latAccum += subArray->readLatencyAccum; latOther += subArray->readLatencyOther;
		eTot += subArray->readDynamicEnergy; eADCcat += subArray->readDynamicEnergyADC; eAccumCat += subArray->readDynamicEnergyAccum; eOtherCat += subArray->readDynamicEnergyOther;
		eArray += subArray->readDynamicEnergyArray;
		eMLSA += subArray->SARADC ? 0 : subArray->multilevelSenseAmp.readDynamicEnergy;
		eEnc += subArray->SARADC ? 0 : subArray->multilevelSAEncoder.readDynamicEnergy;
		eSAR += subArray->SARADC ? subArray->sarADC.readDynamicEnergy : 0;
		if (subArray->numColMuxed > 1) { eMux += subArray->mux.readDynamicEnergy; eMuxDec += subArray->muxDecoder.readDynamicEnergy; }
		eWLsw += subArray->wlNewSwitchMatrix.readDynamicEnergy + subArray->wlSwitchMatrix.readDynamicEnergy;
		eSLsw += 0;   // slSwitchMatrix read energy is not added to readDynamicEnergy in V1.4 parallel mode
		if (inputBit > 1) eShiftIn += subArray->shiftAddInput.readDynamicEnergy;
		if (subArray->numCellPerSynapse > 1) eShiftW += subArray->shiftAddWeight.readDynamicEnergy;
		if (subArray->numAdd > 1) { eAdder += subArray->adder.readDynamicEnergy; eDff += subArray->dff.readDynamicEnergy; }
		leakage = subArray->leakage;
	}
	const int numADC = (int)ceil((double)subArray->numCol / (double)subArray->numColMuxed);
	const double conversions = (double)subArray->numCol * subArray->numAdd * inputBit;   // each column digitised once per bit-plane per row-group
	double adcEnergyTotal = eMLSA + eEnc + eSAR;
	double adcEnergyPerConv = adcEnergyTotal / conversions;

	/* ---- PE (1 subarray) totals via NeuroSim's own ProcessingUnitCalculatePerformance ---- */
	double peLat, peE, peLeak, peLeakSRAM, peBufLat, peBufE, peIcLat, peIcE, peLADC, peLAcc, peLOth, peEADC, peEAcc, peEOth;
	ProcessingUnitCalculatePerformance(subArray, memory, memory, inputVec, 1, 1, 1, 1, rows, cols, inputBit, cell, false,
		&peLat, &peE, &peLeak, &peLeakSRAM, &peBufLat, &peBufE, &peIcLat, &peIcE, &peLADC, &peLAcc, &peLOth, &peEADC, &peEAcc, &peEOth, false, &clkPeriod);

	/* ---- area breakdown (subarray), SubArray.cpp:734-786 ---- */
	SubArray *s = subArray;
	bool ls = (cell.writeVoltage > 1.5);
	double aLevelShift = ls ? (s->wllevelshifter.area + s->bllevelshifter.area + s->sllevelshifter.area) : 0;
	double aMux = (s->numColMuxed > 1) ? s->mux.area : 0, aMuxDec = (s->numColMuxed > 1) ? s->muxDecoder.area : 0;
	double aMLSA = s->SARADC ? 0 : s->multilevelSenseAmp.area, aEnc = s->SARADC ? 0 : s->multilevelSAEncoder.area, aSAR = s->SARADC ? s->sarADC.area : 0;
	double aRefCols = s->SARADC ? 0 : param->arrayheight * param->arraywidthunit * (param->levelOutput - 1) * numADC / param->dumcolshared;
	double aAddDff = (s->numAdd > 1) ? (s->adder.area + s->dff.area) : 0;
	double aWLbuf = s->usedArea - (s->areaArray + aLevelShift + s->wlSwitchMatrix.area + s->wlNewSwitchMatrix.area + s->slSwitchMatrix.area + aMux + aMuxDec + aMLSA + aEnc + s->shiftAddWeight.area + s->shiftAddInput.area + aAddDff + aSAR);

	/* ---- report ---- */
	cout << "=================== NeuroSim V1.4 single-subarray MVM driver ===================" << endl;
	cout << "memcelltype=" << param->memcelltype << " accesstype=" << param->accesstype << " technode=" << param->technode
	     << " rows=" << rows << " cols=" << cols << " cellBit=" << param->cellBit << " synapseBit=" << param->synapseBit
	     << " levelOutput=" << param->levelOutput << " (ADC bits=" << log2((double)param->levelOutput) << ")"
	     << " numBitInput=" << param->numBitInput << " numRowParallel=" << param->numRowParallel << " numColMuxed=" << s->numColMuxed
	     << " SARADC=" << param->SARADC << " currentMode=" << param->currentMode << endl;
	cout << "Ron=" << param->resistanceOn << " Roff=" << param->resistanceOff << " readVoltage=" << param->readVoltage
	     << " accessVoltage=" << param->accessVoltage << " readPulseWidth=" << param->readPulseWidth << " writeVoltage=" << param->writeVoltage
	     << " synchronous=" << param->synchronous << " validated=" << param->validated << endl;
	cout << "mean input bit activity=" << actSum / inputBit << "  mean cell level=" << sumCellLevel / nCells << "  input ones=" << onesTotal << endl;
	cout << "sensing cycle (clkPeriod) = " << sensingCycle_s * 1e9 << " ns; clkFreq used = " << clkFreqUsed / 1e9 << " GHz" << endl;
	cout << "  rowdelay=" << rowdelay_s * 1e9 << " ns  muxdelay=" << muxdelay_s * 1e9 << " ns  ADC(LUT)=" << adcLatencyLUT_s * 1e9 << " ns" << endl;
	cout << "Subarray latency per MVM = " << latCyc * cyc2s * 1e9 << " ns  (" << latCyc << " cycles; ADC " << latADC * cyc2s * 1e9
	     << " ns, accum " << latAccum * cyc2s * 1e9 << " ns, other " << latOther * cyc2s * 1e9 << " ns)" << endl;
	cout << "Subarray read dynamic energy per MVM = " << eTot * 1e12 << " pJ  (NeuroSim categories: ADC+array " << eADCcat * 1e12
	     << ", accum " << eAccumCat * 1e12 << ", other " << eOtherCat * 1e12 << ")" << endl;
	cout << "  array(WL) " << eArray * 1e12 << " pJ, ADC(MLSA) " << eMLSA * 1e12 << ", encoder " << eEnc * 1e12 << ", SAR " << eSAR * 1e12
	     << ", mux " << eMux * 1e12 << ", muxDecoder " << eMuxDec * 1e12 << ", WL switch " << eWLsw * 1e12
	     << ", shiftAddInput " << eShiftIn * 1e12 << ", shiftAddWeight " << eShiftW * 1e12 << ", adder " << eAdder * 1e12 << ", dff " << eDff * 1e12 << endl;
	cout << "ADC: " << numADC << " ADCs/subarray, " << conversions << " conversions/MVM, energy/conversion = " << adcEnergyPerConv * 1e12
	     << " pJ, area/ADC = " << (aMLSA + aEnc + aSAR) / numADC * 1e12 << " um^2" << endl;
	cout << "Subarray leakage = " << leakage * 1e6 << " uW" << endl;
	cout << "Subarray area = " << s->area * 1e12 << " um^2 (H " << s->height * 1e6 << " um x W " << s->width * 1e6 << " um), used " << s->usedArea * 1e12
	     << ", empty " << s->emptyArea * 1e12 << ", array " << s->areaArray * 1e12 << ", ADC " << s->areaADC * 1e12 << ", accum " << s->areaAccum * 1e12
	     << ", other " << s->areaOther * 1e12 << endl;
	cout << "PE(1 subarray): area " << peArea[0] * 1e12 << " um^2; latency " << peLat * cyc2s * 1e9 << " ns; energy " << peE * 1e12
	     << " pJ (buffer " << peBufE * 1e12 << ", ic " << peIcE * 1e12 << "); leakage " << peLeak * 1e6 << " uW" << endl;
	subArray->PrintProperty();

	ostringstream js;
	js << "{";
	js << "\"memcelltype\":" << param->memcelltype << ",\"accesstype\":" << param->accesstype << ",\"technode\":" << param->technode;
	js << ",\"rows\":" << rows << ",\"cols\":" << cols << ",\"cellBit\":" << param->cellBit << ",\"synapseBit\":" << param->synapseBit;
	js << ",\"levelOutput\":" << param->levelOutput << ",\"adcBits\":" << jnum(log2((double)param->levelOutput)) << ",\"inputBits\":" << param->numBitInput;
	js << ",\"numRowParallel\":" << param->numRowParallel << ",\"numColMuxed\":" << s->numColMuxed << ",\"numColPerSynapse\":" << param->numColPerSynapse;
	js << ",\"SARADC\":" << (param->SARADC ? 1 : 0) << ",\"currentMode\":" << (param->currentMode ? 1 : 0) << ",\"synchronous\":" << (param->synchronous ? 1 : 0);
	js << ",\"unsupportedNodeForced\":" << (unsupportedNode ? 1 : 0);
	js << ",\"Ron\":" << jnum(param->resistanceOn) << ",\"Roff\":" << jnum(param->resistanceOff) << ",\"readVoltage\":" << jnum(param->readVoltage);
	js << ",\"accessVoltage\":" << jnum(param->accessVoltage) << ",\"readPulseWidth\":" << jnum(param->readPulseWidth) << ",\"writeVoltage\":" << jnum(param->writeVoltage);
	js << ",\"pInput\":" << jnum(pInput) << ",\"meanActivity\":" << jnum(actSum / inputBit) << ",\"seed\":" << seed;
	js << ",\"sensingCycle_ns\":" << jnum(sensingCycle_s * 1e9) << ",\"clkFreqUsed_GHz\":" << jnum(clkFreqUsed / 1e9);
	js << ",\"rowdelay_ns\":" << jnum(rowdelay_s * 1e9) << ",\"muxdelay_ns\":" << jnum(muxdelay_s * 1e9) << ",\"adcLatencyLUT_ns\":" << jnum(adcLatencyLUT_s * 1e9);
	js << ",\"latency_cycles\":" << jnum(latCyc) << ",\"latency_ns\":" << jnum(latCyc * cyc2s * 1e9);
	js << ",\"latencyADC_ns\":" << jnum(latADC * cyc2s * 1e9) << ",\"latencyAccum_ns\":" << jnum(latAccum * cyc2s * 1e9) << ",\"latencyOther_ns\":" << jnum(latOther * cyc2s * 1e9);
	js << ",\"energy_pJ\":" << jnum(eTot * 1e12) << ",\"energyADCcat_pJ\":" << jnum(eADCcat * 1e12) << ",\"energyAccumCat_pJ\":" << jnum(eAccumCat * 1e12) << ",\"energyOtherCat_pJ\":" << jnum(eOtherCat * 1e12);
	js << ",\"energy_breakdown_pJ\":{\"array_wl\":" << jnum(eArray * 1e12) << ",\"adc_mlsa\":" << jnum(eMLSA * 1e12) << ",\"adc_encoder\":" << jnum(eEnc * 1e12)
	   << ",\"adc_sar\":" << jnum(eSAR * 1e12) << ",\"mux\":" << jnum(eMux * 1e12) << ",\"mux_decoder\":" << jnum(eMuxDec * 1e12) << ",\"wl_switch_matrix\":" << jnum(eWLsw * 1e12)
	   << ",\"shift_add_input\":" << jnum(eShiftIn * 1e12) << ",\"shift_add_weight\":" << jnum(eShiftW * 1e12) << ",\"psum_adder\":" << jnum(eAdder * 1e12) << ",\"psum_dff\":" << jnum(eDff * 1e12) << "}";
	js << ",\"numADC\":" << numADC << ",\"adcConversions\":" << jnum(conversions) << ",\"adcEnergyPerConv_pJ\":" << jnum(adcEnergyPerConv * 1e12);
	js << ",\"adcAreaPerADC_um2\":" << jnum((aMLSA + aEnc + aSAR) / numADC * 1e12);
	js << ",\"leakage_uW\":" << jnum(leakage * 1e6);
	js << ",\"subarrayArea_um2\":" << jnum(s->area * 1e12) << ",\"subarrayHeight_um\":" << jnum(s->height * 1e6) << ",\"subarrayWidth_um\":" << jnum(s->width * 1e6);
	js << ",\"area_breakdown_um2\":{\"array\":" << jnum(s->areaArray * 1e12) << ",\"adc_total\":" << jnum((aMLSA + aEnc + aSAR) * 1e12)
	   << ",\"adc_mlsa_incl_ref_cols\":" << jnum(aMLSA * 1e12) << ",\"adc_ref_cols\":" << jnum(aRefCols * 1e12) << ",\"adc_encoder\":" << jnum(aEnc * 1e12) << ",\"adc_sar\":" << jnum(aSAR * 1e12)
	   << ",\"shift_add_input\":" << jnum(s->shiftAddInput.area * 1e12) << ",\"shift_add_weight\":" << jnum(s->shiftAddWeight.area * 1e12) << ",\"psum_adder_dff\":" << jnum(aAddDff * 1e12)
	   << ",\"wl_switch_matrix\":" << jnum((s->wlSwitchMatrix.area + s->wlNewSwitchMatrix.area) * 1e12) << ",\"sl_switch_matrix\":" << jnum(s->slSwitchMatrix.area * 1e12)
	   << ",\"mux\":" << jnum(aMux * 1e12) << ",\"mux_decoder\":" << jnum(aMuxDec * 1e12) << ",\"level_shifters\":" << jnum(aLevelShift * 1e12) << ",\"wl_repeater_buffers\":" << jnum(aWLbuf * 1e12)
	   << ",\"floorplan_empty\":" << jnum(s->emptyArea * 1e12)
	   << ",\"neurosim_cat_ADC\":" << jnum(s->areaADC * 1e12) << ",\"neurosim_cat_Accum\":" << jnum(s->areaAccum * 1e12) << ",\"neurosim_cat_Other\":" << jnum(s->areaOther * 1e12) << "}";
	js << ",\"pe1\":{\"area_um2\":" << jnum(peArea[0] * 1e12) << ",\"area_ADC_um2\":" << jnum(peArea[1] * 1e12) << ",\"area_Accum_incl_addertree_um2\":" << jnum(peArea[2] * 1e12)
	   << ",\"area_Other_incl_io_buffers_um2\":" << jnum(peArea[3] * 1e12) << ",\"area_Array_um2\":" << jnum(peArea[4] * 1e12)
	   << ",\"io_buffer_area_um2\":" << jnum((peArea[3] - s->areaOther) * 1e12)
	   << ",\"latency_ns\":" << jnum(peLat * cyc2s * 1e9) << ",\"energy_pJ\":" << jnum(peE * 1e12) << ",\"buffer_energy_pJ\":" << jnum(peBufE * 1e12)
	   << ",\"ic_energy_pJ\":" << jnum(peIcE * 1e12) << ",\"leakage_uW\":" << jnum(peLeak * 1e6) << "}";
	js << "}";
	cout << "RESULT_JSON " << js.str() << endl;
	return 0;
}
