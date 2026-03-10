#include <cstdint>

class MovingAverageFilter_4Tap {
private:
    uint8_t s0;
    uint8_t s1;
    uint8_t s2;
    uint8_t s3;
    uint8_t data_out;

public:
    MovingAverageFilter_4Tap() {
        s0 = 0;
        s1 = 0;
        s2 = 0;
        s3 = 0;
        data_out = 0;
    }

    uint8_t evaluate(bool rst, uint8_t data_in) {
        #pragma HLS INTERFACE s_axilite port=rst
        #pragma HLS INTERFACE s_axilite port=data_in
        #pragma HLS INTERFACE s_axilite port=return

        if (rst) {
            s0 = 0;
            s1 = 0;
            s2 = 0;
            s3 = 0;
        } else {
            s3 = s2;
            s2 = s1;
            s1 = s0;
            s0 = data_in;
        }

        uint16_t sum_val = (uint16_t)s0 + (uint16_t)s1 + (uint16_t)s2 + (uint16_t)s3;
        uint8_t avg_result = sum_val / 4;

        data_out = avg_result;

        return data_out;
    }
};