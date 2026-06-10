#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace huffcore {

std::string sha256_hex_buffer(const std::vector<unsigned char>& data);

} // namespace huffcore
