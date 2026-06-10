#include "entropy.h"
#include <cmath>
#include <array>

namespace huffcore {

double shannon_entropy(const std::vector<unsigned char>& data) {
    if (data.empty()) {
        return 0.0;
    }

    std::array<size_t, 256> counts = {};
    for (unsigned char byte : data) {
        counts[byte]++;
    }

    const double length = static_cast<double>(data.size());
    double entropy = 0.0;
    for (size_t freq : counts) {
        if (freq == 0) {
            continue;
        }
        const double p = static_cast<double>(freq) / length;
        entropy -= p * std::log2(p);
    }
    return entropy;
}

} // namespace huffcore
