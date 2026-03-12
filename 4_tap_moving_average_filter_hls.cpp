#ifndef FIR_FILTER_H
#define FIR_FILTER_H

struct FirState {
    unsigned short tap0_reg;
    unsigned short tap1_reg;
    unsigned short tap2_reg;
};

#pragma hls_top
unsigned char fir_filter(unsigned char data_in, bool rst_n, FirState &state) {
    if (!rst_n) {
        state.tap0_reg = 0;
        state.tap1_reg = 0;
        state.tap2_reg = 0;
        return 0;
    }

    unsigned short current_tap0 = state.tap0_reg;
    unsigned short current_tap1 = state.tap1_reg;
    unsigned short current_tap2 = state.tap2_reg;

    unsigned short sum_val = (data_in + current_tap0) & 0x3FF;
    sum_val = (sum_val + current_tap1) & 0x3FF;
    sum_val = (sum_val + current_tap2) & 0x3FF;

    unsigned char data_out = (unsigned char)((sum_val >> 2) & 0xFF);

    state.tap2_reg = current_tap1;
    state.tap1_reg = current_tap0;
    state.tap0_reg = (unsigned short)(data_in & 0xFF);

    return data_out;
}

#endif