// element-rate datapath only: decode -> shift-add product -> block accumulate
// (the once-per-32-cycles block->FP32 + row-accumulate path is multi-cycle)
`default_nettype none
module element_path (
    input wire clk, input wire rst_n, input wire in_valid, input wire blk_start,
    input wire [3:0] w_code, input wire [7:0] a_code,
    output logic signed [29:0] acc_out
);
    logic [3:0] k_mag;
    always_comb begin
        unique case (w_code[2:0])
            3'd0: k_mag=4'd0; 3'd1: k_mag=4'd1; 3'd2: k_mag=4'd2; 3'd3: k_mag=4'd3;
            3'd4: k_mag=4'd4; 3'd5: k_mag=4'd6; 3'd6: k_mag=4'd8; default: k_mag=4'd12;
        endcase
    end
    wire [3:0] a_sig  = (a_code[6:3] != 4'd0) ? {1'b1, a_code[2:0]} : {1'b0, a_code[2:0]};
    wire [3:0] a_eeff = (a_code[6:3] != 4'd0) ? a_code[6:3] : 4'd1;
    logic [7:0] prod_mag;
    always_comb prod_mag = (k_mag[0]?{4'b0,a_sig}:8'd0) + (k_mag[1]?{3'b0,a_sig,1'b0}:8'd0)
                         + (k_mag[2]?{2'b0,a_sig,2'b0}:8'd0) + (k_mag[3]?{1'b0,a_sig,3'b0}:8'd0);
    wire [22:0] shifted = {15'd0, prod_mag} << a_eeff;
    wire signed [29:0] addend = (w_code[3]^a_code[7]) ? -$signed({7'd0,shifted}) : $signed({7'd0,shifted});
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) acc_out <= '0;
        else if (in_valid) acc_out <= blk_start ? addend : acc_out + addend;
    end
endmodule
`default_nettype wire
