// Verilator testbench: drives vectors from rtl/golden_model.py through
// k3_nand_reducer and checks the 8 row accumulators bit-for-bit.
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>
#include "Vk3_nand_reducer.h"
#include "verilated.h"

static void tick(Vk3_nand_reducer* dut) {
    dut->clk = 0; dut->eval();
    dut->clk = 1; dut->eval();
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    const char* path = argc > 1 ? argv[1] : "vectors.txt";
    std::ifstream f(path);
    if (!f) { fprintf(stderr, "cannot open %s\n", path); return 2; }

    auto* dut = new Vk3_nand_reducer;
    dut->rst_n = 0; dut->in_valid = 0; dut->row_clear = 0;
    tick(dut); tick(dut);
    dut->rst_n = 1; tick(dut);

    int n_blocks; f >> n_blocks;
    for (int b = 0; b < n_blocks; b++) {
        int row, wsc, asc; f >> row >> wsc >> asc;
        for (int i = 0; i < 32; i++) {
            int w, a; f >> w >> a;
            dut->in_valid = 1;
            dut->w_code = w; dut->a_code = a;
            dut->blk_start = (i == 0); dut->blk_end = (i == 31);
            dut->w_scale = wsc; dut->a_scale = asc;
            dut->row_sel = row;
            tick(dut);
        }
        dut->in_valid = 0; dut->blk_start = 0; dut->blk_end = 0;
        tick(dut);   // blk_done cycle -> row accumulate
        tick(dut);
    }

    int fails = 0;
    for (int r = 0; r < 8; r++) {
        unsigned exp; f >> std::hex >> exp;
        dut->row_sel = r; dut->eval();
        unsigned got = dut->row_value;
        if (got != exp) {
            printf("row %d MISMATCH: got %08x exp %08x\n", r, got, exp);
            fails++;
        }
    }
    printf(fails ? "TB FAIL (%d rows)\n" : "TB PASS: %d blocks (%d elems), 8 rows bit-exact\n",
           fails ? fails : n_blocks, n_blocks * 32);
    delete dut;
    return fails ? 1 : 0;
}
