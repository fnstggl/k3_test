// k3_nand_reducer.sv — minimal per-plane MXFP4 x MXFP8 dot-product reducer
// for K3-on-NAND (Gate 7 fallback: the D_ACC primitive from Gate 4).
//
// Scope: ONE lane. It consumes one (weight, activation) element pair per cycle
// from the page buffer / broadcast register, accumulates a 32-element MX block
// in fixed point, applies the two E8M0 block scales, converts to FP32 and
// accumulates into one of R=8 retained row accumulators with a truncating
// FP32 adder. No multiplier array anywhere: the E2M1 weight magnitude is
// {0,.5,1,1.5,2,3,4,6} = k/2 with k in {0,1,2,3,4,6,8,12}, so the product is
// a 4-term conditional shift-add; the E4M3 exponent is applied as a barrel
// shift into a 30-bit block accumulator.
//
// Rounding: block->FP32 conversion and the FP32 accumulate TRUNCATE toward
// zero (documented; mirrored exactly by the Python golden model
// rtl/golden_model.py; numerical error vs exact math is reported by the TB).
//
// This file is intentionally plain synchronous SystemVerilog (no memories,
// no vendor cells) so Yosys/OpenROAD-class flows give a meaningful first-order
// area/timing estimate for "tiny vs non-tiny".

`default_nettype none

module k3_nand_reducer #(
    parameter int N_ROWS = 8          // retained row accumulators per lane
) (
    input  wire        clk,
    input  wire        rst_n,

    // element stream (one MX element pair per cycle)
    input  wire        in_valid,
    input  wire [3:0]  w_code,       // E2M1: {sign, exp[1:0], mant}
    input  wire [7:0]  a_code,       // E4M3: {sign, exp[3:0], mant[2:0]}
    input  wire        blk_start,    // first element of a 32-block
    input  wire        blk_end,      // last element of a 32-block
    input  wire [7:0]  w_scale,      // E8M0 code for the weight block
    input  wire [7:0]  a_scale,      // E8M0 code for the activation block
    input  wire [2:0]  row_sel,      // destination row accumulator

    // row accumulator control
    input  wire        row_clear,    // clear row_sel's accumulator
    output wire [31:0] row_value,    // FP32 value of row_sel's accumulator

    output wire        busy          // block scale/convert in flight
);

    // ------------------------------------------------------------------
    // element decode
    // ------------------------------------------------------------------
    // E2M1 magnitude in half-units: k = {0,1,2,3,4,6,8,12}
    logic [3:0] k_mag;
    always_comb begin
        unique case (w_code[2:0])
            3'd0: k_mag = 4'd0;
            3'd1: k_mag = 4'd1;
            3'd2: k_mag = 4'd2;
            3'd3: k_mag = 4'd3;
            3'd4: k_mag = 4'd4;
            3'd5: k_mag = 4'd6;
            3'd6: k_mag = 4'd8;
            default: k_mag = 4'd12;
        endcase
    end
    wire w_sign = w_code[3];

    wire        a_sign = a_code[7];
    wire [3:0]  a_exp  = a_code[6:3];
    wire [2:0]  a_man  = a_code[2:0];
    // significand: normals 8+m, subnormals m; effective exponent max(e,1)
    wire [3:0]  a_sig  = (a_exp != 4'd0) ? {1'b1, a_man} : {1'b0, a_man};
    wire [3:0]  a_eeff = (a_exp != 4'd0) ? a_exp : 4'd1;

    // ------------------------------------------------------------------
    // product: (k * a_sig) << a_eeff   — 4-term conditional shift-add
    // max k*a_sig = 12*15 = 180 (8 bits); << up to 15 -> 23 bits magnitude
    // ------------------------------------------------------------------
    logic [7:0] prod_mag;
    always_comb begin
        prod_mag = (k_mag[0] ? {4'b0, a_sig}        : 8'd0)
                 + (k_mag[1] ? {3'b0, a_sig, 1'b0}  : 8'd0)
                 + (k_mag[2] ? {2'b0, a_sig, 2'b0}  : 8'd0)
                 + (k_mag[3] ? {1'b0, a_sig, 3'b0}  : 8'd0);
    end
    wire [22:0] shifted = {15'd0, prod_mag} << a_eeff;
    wire        p_sign  = w_sign ^ a_sign;
    wire signed [29:0] addend = p_sign ? -$signed({7'd0, shifted})
                                       :  $signed({7'd0, shifted});

    // ------------------------------------------------------------------
    // 32-element block accumulator (fixed point, exact)
    // |sum| <= 32*180*2^15 = 188.7e6 < 2^28 -> 30-bit signed is safe
    // ------------------------------------------------------------------
    logic signed [29:0] blk_acc;
    logic [7:0]  wsc_q, asc_q;
    logic        blk_done;           // captured block ready for convert
    logic signed [29:0] blk_acc_q;
    logic [2:0]  row_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            blk_acc  <= '0;
            blk_done <= 1'b0;
            blk_acc_q <= '0;
            wsc_q <= '0; asc_q <= '0; row_q <= '0;
        end else begin
            blk_done <= 1'b0;
            if (in_valid) begin
                if (blk_start) begin
                    blk_acc <= addend;
                    wsc_q   <= w_scale;
                    asc_q   <= a_scale;
                end else begin
                    blk_acc <= blk_acc + addend;
                end
                if (blk_end) begin
                    blk_acc_q <= blk_start ? addend : (blk_acc + addend);
                    row_q     <= row_sel;
                    blk_done  <= 1'b1;
                end
            end
        end
    end

    // ------------------------------------------------------------------
    // block -> FP32 (truncating) : value = blk_acc * 2^(wsc+asc-254-11)
    //   -11 = -1 (k in halves) - 10 (E4M3 sig scaling: sig*2^(E-10))
    // ------------------------------------------------------------------
    wire        c_sign = blk_acc_q[29];
    wire [29:0] c_mag  = c_sign ? (~blk_acc_q + 30'd1) : blk_acc_q;

    // leading-zero count of 30-bit magnitude
    logic [4:0] lzc;
    always_comb begin
        lzc = 5'd30;
        for (int i = 0; i < 30; i++) begin
            if (c_mag[i]) lzc = 5'(29 - i);   // last set bit wins
        end
    end
    wire        c_zero = (c_mag == 30'd0);
    // msb position p = 29-lzc; value = mag = M, exponent contribution p
    wire [4:0]  msb_pos = 5'd29 - lzc;
    // normalize magnitude to [2^29, 2^30) then take stored mantissa (truncate);
    // norm[29] is the implicit leading 1, norm[5:0] are truncated by design
    /* verilator lint_off UNUSEDSIGNAL */
    wire [29:0] norm = c_mag << lzc;
    /* verilator lint_on UNUSEDSIGNAL */
    wire [22:0] fmant23 = norm[28:6];
    // FP32 exponent: 127 + msb_pos + (wsc-127) + (asc-127) - 11
    wire signed [11:0] ebase = 12'sd127 + $signed({7'd0, msb_pos})
                             + $signed({4'd0, wsc_q}) - 12'sd127
                             + $signed({4'd0, asc_q}) - 12'sd127
                             - 12'sd11;
    // clamp (weights/activations of real K3 never hit these rails; TB checks)
    wire [7:0] fexp = c_zero ? 8'd0
                    : (ebase <= 12'sd0)   ? 8'd0
                    : (ebase >= 12'sd255) ? 8'd254
                    : ebase[7:0];
    wire [31:0] blk_fp32 = c_zero ? 32'd0
                         : {c_sign, fexp, fmant23};

    // ------------------------------------------------------------------
    // FP32 row accumulate (truncating adder, 1 block per ~cycle max rate/32)
    // ------------------------------------------------------------------
    logic [31:0] rows [N_ROWS];

    function automatic [31:0] fp32_add_trunc(input [31:0] a, input [31:0] b);
        logic sa2, sb2; logic [7:0] ea2, eb2; logic [23:0] ma2, mb2;
        logic [7:0] eg; logic [26:0] mg, ml;   // guard headroom
        logic [4:0] d;
        logic sr; logic [27:0] sum;
        logic [7:0] er; logic [4:0] lz2;
        begin
            if (a[30:0] == 31'd0) fp32_add_trunc = b;
            else if (b[30:0] == 31'd0) fp32_add_trunc = a;
            else begin
                sa2 = a[31]; ea2 = a[30:23]; ma2 = {1'b1, a[22:0]};
                sb2 = b[31]; eb2 = b[30:23]; mb2 = {1'b1, b[22:0]};
                if ({ea2, ma2} >= {eb2, mb2}) begin
                    eg = ea2; mg = {ma2, 3'b0}; sr = sa2;
                    d  = (ea2 - eb2 > 8'd26) ? 5'd26 : 5'(ea2 - eb2);
                    ml = {mb2, 3'b0} >> d;
                    if (sa2 == sb2) sum = {1'b0, mg} + {1'b0, ml};
                    else            sum = {1'b0, mg} - {1'b0, ml};
                end else begin
                    eg = eb2; mg = {mb2, 3'b0}; sr = sb2;
                    d  = (eb2 - ea2 > 8'd26) ? 5'd26 : 5'(eb2 - ea2);
                    ml = {ma2, 3'b0} >> d;
                    if (sa2 == sb2) sum = {1'b0, mg} + {1'b0, ml};
                    else            sum = {1'b0, mg} - {1'b0, ml};
                end
                if (sum == 28'd0) fp32_add_trunc = 32'd0;
                else begin
                    // normalize: last-set-bit scan (no break, yosys-friendly)
                    lz2 = 5'd0;
                    for (int i = 0; i < 28; i++) begin
                        if (sum[i]) lz2 = 5'(27 - i);
                    end
                    // reference point: msb at bit 26 (1.xx with 3 guard bits)
                    if (lz2 <= 5'd1) begin
                        sum = sum >> (5'd1 - lz2);
                        er  = eg + (8'd1 - {3'd0, lz2});
                    end else begin
                        sum = sum << (lz2 - 5'd1);
                        er  = eg - ({3'd0, lz2} - 8'd1);
                    end
                    fp32_add_trunc = {sr, er, sum[25:3]};
                end
            end
        end
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < N_ROWS; i++) rows[i] <= 32'd0;
        end else begin
            if (row_clear) rows[row_sel] <= 32'd0;
            else if (blk_done) rows[row_q] <= fp32_add_trunc(rows[row_q], blk_fp32);
        end
    end

    assign row_value = rows[row_sel];
    assign busy = blk_done;

endmodule

`default_nettype wire
