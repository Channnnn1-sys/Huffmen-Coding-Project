#pragma once

#include <string>
#include <unordered_map>
#include <vector>

namespace huffcore {

std::unordered_map<unsigned char, std::string> build_huffman_codes(
    const std::vector<size_t>& frequencies
);

std::unordered_map<unsigned char, unsigned int> build_code_lengths(
    const std::unordered_map<unsigned char, std::string>& codes
);

} // namespace huffcore
