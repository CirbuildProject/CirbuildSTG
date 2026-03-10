#include "4_tap_moving_average_filter_hls.cpp"

#include <iostream>
#include <cstdint>
#include <cassert>
#include <deque>

int main() {
    std::deque<uint8_t> shadow_taps = {0, 0, 0, 0};
    
    moving_average_filter(0, false);
    
    uint8_t test_inputs[] = {10, 20, 30, 40, 255, 255, 0, 1, 2, 3};
    
    for (uint8_t val : test_inputs) {
        shadow_taps.push_front(val);
        shadow_taps.pop_back();
        
        uint16_t expected_sum = 0;
        for (uint8_t t : shadow_taps) expected_sum += t;
        uint8_t expected_avg = expected_sum / 4;
        
        uint8_t hw_out = moving_average_filter(val, true);
        
        if (hw_out != expected_avg) {
            return 1;
        }
    }
    
    moving_average_filter(0, false);
    uint8_t post_reset = moving_average_filter(0, true);
    if (post_reset != 0) return 1;
    
    for (int i = 0; i < 100; ++i) {
        uint8_t val = (uint8_t)(i % 256);
        shadow_taps.push_front(val);
        shadow_taps.pop_back();
        uint16_t sum = 0;
        for (uint8_t t : shadow_taps) sum += t;
        if (moving_average_filter(val, true) != (sum / 4)) return 1;
    }
    
    std::cout << "TEST PASSED" << std::endl;
    return 0;
}