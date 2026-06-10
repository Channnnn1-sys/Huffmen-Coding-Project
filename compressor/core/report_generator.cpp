#include "report_generator.h"
#include <sstream>

namespace huffcore {

static std::string quote(const std::string& value) {
    std::ostringstream escaped;
    escaped << '"';
    for (char c : value) {
        switch (c) {
            case '"': escaped << "\\\""; break;
            case '\\': escaped << "\\\\"; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default: escaped << c; break;
        }
    }
    escaped << '"';
    return escaped.str();
}

std::string create_metadata_json(
    const std::string& algorithm,
    const std::string& original_filename,
    const std::string& compressed_filename,
    size_t original_size,
    size_t compressed_size,
    const std::string& sha256,
    const std::string& timestamp
) {
    std::ostringstream json;
    json << "{"
         << "\"algorithm\":" << quote(algorithm) << ","
         << "\"original_filename\":" << quote(original_filename) << ","
         << "\"compressed_filename\":" << quote(compressed_filename) << ","
         << "\"original_size\":" << original_size << ","
         << "\"compressed_size\":" << compressed_size << ","
         << "\"sha256\":" << quote(sha256) << ","
         << "\"timestamp\":" << quote(timestamp)
         << "}";
    return json.str();
}

std::string create_decompression_metadata_json(
    const std::string& algorithm,
    const std::string& original_compressed,
    const std::string& decompressed_filename,
    size_t compressed_size,
    size_t decompressed_size,
    const std::string& timestamp
) {
    std::ostringstream json;
    json << "{"
         << "\"algorithm\":" << quote(algorithm) << ","
         << "\"original_compressed\":" << quote(original_compressed) << ","
         << "\"decompressed_filename\":" << quote(decompressed_filename) << ","
         << "\"compressed_size\":" << compressed_size << ","
         << "\"decompressed_size\":" << decompressed_size << ","
         << "\"timestamp\":" << quote(timestamp)
         << "}";
    return json.str();
}

} // namespace huffcore
