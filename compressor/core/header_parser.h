#pragma once

#include <filesystem>
#include <string>
#include <unordered_map>

namespace huffcore {

struct HeaderInfo {
    int unique_symbol_count = 0;
    int total_symbol_count = 0;
    std::string original_extension;
};

bool parse_archive_header(
    const std::filesystem::path& compressed_path,
    HeaderInfo& header_info,
    std::unordered_map<std::string, unsigned char>& code_map,
    std::string& error_message
);

} // namespace huffcore
