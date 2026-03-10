#include "ap_int.h"

// Function representing a 4-tap Moving Average Filter
// This function processes one sample per clock cycle.
// The internal state (s0-s3) is maintained using static variables.
// 'rst' is an active-high reset signal.
ap_uint<8> moving_average_filter_4tap(
    ap_uint<8> data_in, // 8-bit unsigned input data
    ap_uint<1> rst      // 1-bit reset signal (active high)
) {
    // HLS Pragmas for interface and pipeline
    #pragma HLS INTERFACE ap_none port=data_in
    #pragma HLS INTERFACE ap_none port=rst
    #pragma HLS INTERFACE ap_none port=return // The return value is the output data
    #pragma HLS PIPELINE II=1 // Achieve a new output every clock cycle

    // Internal Registers, 8-bit UNSIGNED
    // 'static' keyword ensures these variables retain their values across function calls
    // and are synthesized as flip-flops.
    static ap_uint<8> s0 = 0;
    static ap_uint<8> s1 = 0;
    static ap_uint<8> s2 = 0;
    static ap_uint<8> s3 = 0;

    // --- Sequential Logic (triggered by clock edge, reset is dominant) ---
    if (rst == 1) {
        // Reset all internal registers to 0
        s0 = 0;
        s1 = 0;
        s2 = 0;
        s3 = 0;
    } else {
        // Shift register update on the positive clock edge
        s3 = s2;
        s2 = s1;
        s1 = s0;
        s0 = data_in; // New input data shifts into the first register
    }

    // --- Combinational Logic ---
    // Calculate the sum of the four taps.
    // The sum can be up to 4 * 255 = 1020, which requires 10 bits (2^10 = 1024).
    ap_uint<10> current_sum = s0 + s1 + s2 + s3;

    // Calculate the average by integer division.
    // The average can be up to 1020 / 4 = 255, which fits in 8 bits.
    ap_uint<8> avg_result = current_sum / 4;

    // --- Output Assignment ---
    // The result is directly returned as the function's output.
    return avg_result;
}