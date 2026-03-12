#include "4_tap_moving_average_filter_hls.cpp"

#include <iostream>
#include <deque>
#include <cstdint>
#include "4_tap_moving_average_filter_hls.cpp"

int main() {
    FirState state;
    std::deque<uint8_t> shadow_buffer;

    auto reset_system = [&]() {
        fir_filter(0, false, state);
        shadow_buffer.clear();
        for (int i = 0; i < 3; ++i) shadow_buffer.push_back(0);
    };

    reset_system();

    for (int i = 0; i < 100; ++i) {
        uint8_t input_val = (uint8_t)(i % 256);
        
        uint16_t sum = input_val;
        for (uint8_t val : shadow_buffer) {
            sum += val;
        }
        uint8_t expected_out = (uint8_t)(sum >> 2);

        uint8_t hw_out = fir_filter(input_val, true, state);

        if (hw_out != expected_out) {
            return 1;
        }

        shadow_buffer.push_front(input_val);
        if (shadow_buffer.size() > 3) {
            shadow_buffer.pop_back();
        }
    }

    reset_system();
    uint8_t hw_out_after_rst = fir_filter(100, true, state);
    if (hw_out_after_rst != (100 >> 2)) {
        return 1;
    }

    std::cout << "TEST PASSED" << std::endl;
    return 0;
}