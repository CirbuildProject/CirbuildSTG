#include "4_tap_moving_average_filter_hls.cpp"

#include <iostream>
#include <deque>
#include <cstdint>

int main() {
    MovingAverageFilter4Tap state;
    std::deque<uint8_t> shadow_history;
    uint8_t hw_out = 0;

    moving_average_filter_4tap(0, false, hw_out, state);
    shadow_history.clear();
    for (int i = 0; i < 4; ++i) shadow_history.push_front(0);

    uint8_t test_inputs[] = {10, 20, 30, 40, 50, 100, 255, 255, 255, 255, 0, 0, 0, 0, 128, 64};
    int num_tests = sizeof(test_inputs) / sizeof(test_inputs[0]);

    for (int i = 0; i < num_tests; ++i) {
        uint8_t current_input = test_inputs[i];
        
        shadow_history.push_front(current_input);
        if (shadow_history.size() > 4) {
            shadow_history.pop_back();
        }

        uint32_t expected_sum = 0;
        for (uint8_t val : shadow_history) {
            expected_sum += val;
        }
        uint8_t expected_out = (uint8_t)(expected_sum / 4);

        moving_average_filter_4tap(current_input, true, hw_out, state);

        if (hw_out != expected_out) {
            std::cerr << "Mismatch at index " << i << ": Expected " << (int)expected_out << " but got " << (int)hw_out << std::endl;
            return 1;
        }
    }

    moving_average_filter_4tap(0, false, hw_out, state);
    if (hw_out != 0) return 1;

    std::cout << "TEST PASSED" << std::endl;
    return 0;
}