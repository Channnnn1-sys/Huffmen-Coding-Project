#pragma once

#include <filesystem>
#include <string>
#include <unordered_map>
#include <vector>

namespace huffcore {

struct ReportEntry {
    std::string key;
    std::string value;
};

std::string create_metadata_json(
    const std::string& algorithm,
    const std::string& original_filename,
    const std::string& compressed_filename,
    size_t original_size,
    size_t compressed_size,
    const std::string& sha256,
    const std::string& timestamp
);

std::string create_decompression_metadata_json(
    const std::string& algorithm,
    const std::string& original_compressed,
    const std::string& decompressed_filename,
    size_t compressed_size,
    size_t decompressed_size,
    const std::string& timestamp
);

} // namespace huffcore
