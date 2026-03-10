#include <cstdint>

struct MovingAverageState {
    uint8_t taps[4];
};

class MovingAverageFilter {
public:
    MovingAverageState state;

    MovingAverageFilter() {
        for (int i = 0; i < 4; ++i) {
            state.taps[i] = 0;
        }
    }

    uint8_t process(uint8_t data_in, bool rst_n) {
        if (!rst_n) {
            for (int i = 0; i < 4; ++i) {
                state.taps[i] = 0;
            }
            return 0;
        }

        state.taps[3] = state.taps[2];
        state.taps[2] = state.taps[1];
        state.taps[1] = state.taps[0];
        state.taps[0] = data_in;

        uint16_t sum_val = 0;
        for (int i = 0; i < 4; ++i) {
            sum_val += state.taps[i];
        }

        uint8_t average = (uint8_t)((sum_val >> 2) & 0xFF);
        return average;
    }
};

#pragma hls_top
uint8_t moving_average_filter(uint8_t data_in, bool rst_n) {
    static MovingAverageFilter filter;
    return filter.process(data_in, rst_n);
}