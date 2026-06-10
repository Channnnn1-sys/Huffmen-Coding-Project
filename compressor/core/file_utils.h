#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace huffcore {
namespace fs = std::filesystem;

bool file_exists(const fs::path& path);
size_t file_size(const fs::path& path);
std::vector<unsigned char> read_file_bytes(const fs::path& path, size_t max_bytes = 0);
std::string file_extension(const fs::path& path);
std::string file_stem(const fs::path& path);
fs::path compressed_output_path(const fs::path& input_path);
fs::path decompressed_output_path(const fs::path& input_path, const std::string& original_extension);
fs::path generated_metadata_path(const fs::path& base_path, const std::string& suffix);
std::string current_timestamp();
std::string escape_json(const std::string& value);
}
