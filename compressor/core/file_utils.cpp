#include "file_utils.h"

#include <chrono>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace huffcore {

bool file_exists(const fs::path& path) {
    return fs::exists(path) && fs::is_regular_file(path);
}

size_t file_size(const fs::path& path) {
    if (!file_exists(path)) {
        return 0;
    }
    return static_cast<size_t>(fs::file_size(path));
}

std::vector<unsigned char> read_file_bytes(const fs::path& path, size_t max_bytes) {
    std::vector<unsigned char> contents;
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return contents;
    }

    const size_t buffer_size = 8192;
    std::vector<char> buffer(buffer_size);
    size_t bytes_read = 0;

    while (input.read(buffer.data(), static_cast<std::streamsize>(buffer.size())) || input.gcount() > 0) {
        const std::streamsize count = input.gcount();
        contents.insert(contents.end(), buffer.data(), buffer.data() + count);
        bytes_read += static_cast<size_t>(count);
        if (max_bytes > 0 && bytes_read >= max_bytes) {
            contents.resize(max_bytes);
            break;
        }
    }

    return contents;
}

std::string file_extension(const fs::path& path) {
    auto ext = path.extension().string();
    if (!ext.empty() && ext[0] == '.') {
        ext.erase(0, 1);
    }
    return ext;
}

std::string file_stem(const fs::path& path) {
    return path.stem().string();
}

fs::path compressed_output_path(const fs::path& input_path) {
    const std::string stem = file_stem(input_path);
    return input_path.parent_path() / (stem + "-compressed.bin");
}

fs::path decompressed_output_path(const fs::path& input_path, const std::string& original_extension) {
    std::string stem = file_stem(input_path);
    const std::string marker = "-compressed";
    if (stem.size() > marker.size() && stem.substr(stem.size() - marker.size()) == marker) {
        stem = stem.substr(0, stem.size() - marker.size());
    }
    return input_path.parent_path() / (stem + "-decompressed" + original_extension);
}

fs::path generated_metadata_path(const fs::path& base_path, const std::string& suffix) {
    return base_path.parent_path() / (base_path.stem().string() + suffix + ".json");
}

std::string current_timestamp() {
    const auto now = std::chrono::system_clock::now();
    const auto time_t_now = std::chrono::system_clock::to_time_t(now);
    std::tm tm_buffer;
#if defined(_WIN32)
    localtime_s(&tm_buffer, &time_t_now);
#else
    localtime_r(&time_t_now, &tm_buffer);
#endif
    std::ostringstream output;
    output << std::put_time(&tm_buffer, "%Y-%m-%dT%H:%M:%S");
    return output.str();
}

std::string escape_json(const std::string& value) {
    std::ostringstream escaped;
    for (const char ch : value) {
        switch (ch) {
            case '\\': escaped << "\\\\"; break;
            case '"': escaped << "\\\""; break;
            case '\b': escaped << "\\b"; break;
            case '\f': escaped << "\\f"; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default:
                if (static_cast<unsigned char>(ch) < 0x20) {
                    escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(ch);
                } else {
                    escaped << ch;
                }
        }
    }
    return escaped.str();
}

} // namespace huffcore
