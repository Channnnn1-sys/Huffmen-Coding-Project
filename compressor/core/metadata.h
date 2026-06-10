#pragma once

#include <filesystem>
#include <string>
#include <unordered_map>
#include <vector>

namespace huffcore {

struct SymbolStats {
    unsigned char symbol;
    size_t frequency;
    unsigned int code_length;
};

struct CompressionReport {
    size_t original_size;
    size_t compressed_size;
    double compression_ratio;
    size_t saved_bytes;
    double entropy;
    double average_bits_per_symbol;
    double efficiency_vs_8bit;
    std::vector<SymbolStats> top_symbols;
    std::string file_extension;
    std::string sha256;
    std::string entropy_warning;
};

struct HeaderInfo {
    int unique_symbol_count;
    int total_symbol_count;
    std::string original_extension;
};

CompressionReport generate_compression_report(
    const std::filesystem::path& input_path,
    const std::filesystem::path& output_path,
    const std::unordered_map<unsigned char, unsigned int>& code_lengths,
    const std::vector<size_t>& frequencies,
    double entropy_value
);

std::string report_to_json(const CompressionReport& report);

} // namespace huffcore
