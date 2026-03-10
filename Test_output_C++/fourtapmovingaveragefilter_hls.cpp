#include "ap_int.h"

void four_tap_moving_average_filter(
    ap_uint<1> rst,
    ap_uint<8> data_in,
    ap_uint<8>& data_out
) {
    #pragma HLS INTERFACE ap_ctrl_hs port=return
    #pragma HLS INTERFACE ap_none port=rst
    #pragma HLS INTERFACE ap_vld port=data_in
    #pragma HLS INTERFACE ap_vld port=data_out
    #pragma HLS PIPELINE II=1

    static ap_uint<8> tap0 = 0;
    static ap_uint<8> tap1 = 0;
    static ap_uint<8> tap2 = 0;
    static ap_uint<8> tap3 = 0;

    ap_uint<10> sum_intermediate = tap0 + tap1 + tap2 + tap3;

    data_out = sum_intermediate / 4;

    if (rst == 1) {
        tap0 = 0;
        tap1 = 0;
        tap2 = 0;
        tap3 = 0;
    } else {
        tap3 = tap2;
        tap2 = tap1;
        tap1 = tap0;
        tap0 = data_in;
    }
}