#pragma once

#include <filesystem>
#include <string>

namespace huffcore {
namespace fs = std::filesystem;

std::string sha256_hex(const fs::path& path);

} // namespace huffcore
