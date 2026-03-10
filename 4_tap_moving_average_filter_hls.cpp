#include <cstdint>

class FourTapMovingAverageFilter {
private:
    uint8_t tap0;
    uint8_t tap1;
    uint8_t tap2;
    uint8_t tap3;
    uint8_t data_out_reg;

public:
    FourTapMovingAverageFilter() : tap0(0), tap1(0), tap2(0), tap3(0), data_out_reg(0) {}

    #pragma hls_top
    uint8_t evaluate(uint8_t data_in, bool rst_n) {
        if (!rst_n) {
            tap0 = 0;
            tap1 = 0;
            tap2 = 0;
            tap3 = 0;
            data_out_reg = 0;
            return 0;
        }

        tap3 = tap2;
        tap2 = tap1;
        tap1 = tap0;
        tap0 = data_in;

        uint16_t sum_val = static_cast<uint16_t>(tap0) + static_cast<uint16_t>(tap1) +
                           static_cast<uint16_t>(tap2) + static_cast<uint16_t>(tap3);

        data_out_reg = static_cast<uint8_t>(sum_val >> 2);

        return data_out_reg;
    }
};