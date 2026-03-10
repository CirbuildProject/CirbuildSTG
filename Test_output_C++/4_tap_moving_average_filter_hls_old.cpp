#include <cstdint>

class MovingAverageFilter {
private:
    uint8_t r0;
    uint8_t r1;
    uint8_t r2;
    uint8_t r3;

public:
    MovingAverageFilter() : r0(0), r1(0), r2(0), r3(0) {}

    #pragma hls_top
    uint8_t update(uint8_t data_in) {
        r3 = r2;
        r2 = r1;
        r1 = r0;
        r0 = data_in;

        uint16_t current_sum = static_cast<uint16_t>(r0) + static_cast<uint16_t>(r1) +
                               static_cast<uint16_t>(r2) + static_cast<uint16_t>(r3);

        uint8_t data_out = static_cast<uint8_t>(current_sum / 4);

        return data_out;
    }
};