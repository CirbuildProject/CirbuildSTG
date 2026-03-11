struct MovingAverageFilter4Tap {
    unsigned char history[4];
    unsigned char data_out;
};

#pragma hls_top
void moving_average_filter_4tap(unsigned char data_in, bool rst_n, unsigned char &data_out, MovingAverageFilter4Tap &state) {
    if (!rst_n) {
        #pragma hls_unroll yes
        for (int i = 0; i < 4; i++) {
            state.history[i] = 0;
        }
        state.data_out = 0;
        data_out = 0;
    } else {
        #pragma hls_unroll yes
        for (int i = 3; i > 0; i--) {
            state.history[i] = state.history[i - 1];
        }
        state.history[0] = data_in;

        unsigned int sum_val = 0;
        #pragma hls_unroll yes
        for (int i = 0; i < 4; i++) {
            sum_val += state.history[i];
        }

        unsigned char avg_val = (unsigned char)((sum_val >> 2) & 0xFF);
        state.data_out = avg_val;
        data_out = state.data_out;
    }
}