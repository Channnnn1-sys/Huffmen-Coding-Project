#include "metadata.h"
#include "file_utils.h"
#include "hashing.h"
#include <algorithm>
#include <numeric>
#include <sstream>

namespace huffcore {

CompressionReport generate_compression_report(
    const std::filesystem::path& input_path,
    const std::filesystem::path& output_path,
    const std::unordered_map<unsigned char, unsigned int>& code_lengths,
    const std::vector<size_t>& frequencies,
    double entropy_value
) {
    CompressionReport report;
    report.original_size = huffcore::file_size(input_path);
    report.compressed_size = huffcore::file_size(output_path);
    report.sha256 = huffcore::sha256_hex(input_path);
    report.entropy = entropy_value;
    report.file_extension = file_extension(input_path);
    report.saved_bytes = (report.original_size > report.compressed_size)
        ? report.original_size - report.compressed_size
        : 0;
    report.entropy_warning = "";
    report.compression_ratio = report.original_size > 0
        ? static_cast<double>(report.compressed_size) / report.original_size * 100.0
        : 0.0;

    const size_t total_symbols = std::accumulate(frequencies.begin(), frequencies.end(), static_cast<size_t>(0));
    double bit_sum = 0.0;
    for (unsigned int b = 0; b < frequencies.size(); ++b) {
        if (frequencies[b] == 0) {
            continue;
        }
        auto it = code_lengths.find(static_cast<unsigned char>(b));
        unsigned int length = it != code_lengths.end() ? it->second : 8;
        bit_sum += static_cast<double>(frequencies[b]) * static_cast<double>(length);
    }

    report.average_bits_per_symbol = total_symbols > 0 ? bit_sum / static_cast<double>(total_symbols) : 0.0;
    report.efficiency_vs_8bit = report.average_bits_per_symbol > 0.0
        ? std::max(0.0, (8.0 - report.average_bits_per_symbol) / 8.0 * 100.0)
        : 0.0;

    std::vector<SymbolStats> symbols;
    for (unsigned int b = 0; b < frequencies.size(); ++b) {
        if (frequencies[b] == 0) {
            continue;
        }
        SymbolStats stats;
        stats.symbol = static_cast<unsigned char>(b);
        stats.frequency = frequencies[b];
        auto it = code_lengths.find(static_cast<unsigned char>(b));
        stats.code_length = it != code_lengths.end() ? it->second : 8;
        symbols.push_back(stats);
    }

    std::sort(symbols.begin(), symbols.end(), [](const SymbolStats& a, const SymbolStats& b) {
        return a.frequency > b.frequency;
    });

    const size_t top_count = std::min(symbols.size(), static_cast<size_t>(5));
    report.top_symbols.assign(symbols.begin(), symbols.begin() + top_count);

    return report;
}

std::string report_to_json(const CompressionReport& report) {
    std::ostringstream json;
    json << "{"
         << "\"original_size\":" << report.original_size << ","
         << "\"compressed_size\":" << report.compressed_size << ","
         << "\"compression_ratio\":" << report.compression_ratio << ","
         << "\"saved_bytes\":" << report.saved_bytes << ","
         << "\"entropy\":" << report.entropy << ","
         << "\"average_bits_per_symbol\":" << report.average_bits_per_symbol << ","
         << "\"efficiency_vs_8bit\":" << report.efficiency_vs_8bit << ","
         << "\"file_extension\":\"" << escape_json(report.file_extension) << "\",";

    json << "\"sha256\":\"" << escape_json(report.sha256) << "\",";
    json << "\"entropy_warning\":\"" << escape_json(report.entropy_warning) << "\",";
    json << "\"top_symbols\":[";
    for (size_t i = 0; i < report.top_symbols.size(); ++i) {
        const auto& entry = report.top_symbols[i];
        json << "{"
             << "\"symbol\":" << static_cast<unsigned int>(entry.symbol) << ","
             << "\"frequency\":" << entry.frequency << ","
             << "\"code_length\":" << entry.code_length
             << "}";
        if (i + 1 < report.top_symbols.size()) {
            json << ",";
        }
    }
    json << "]}";
    return json.str();
}

} // namespace huffcore
