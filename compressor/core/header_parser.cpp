#include "header_parser.h"
#include <fstream>
#include <cstring>

namespace huffcore {

bool parse_archive_header(
    const std::filesystem::path& compressed_path,
    HeaderInfo& header_info,
    std::unordered_map<std::string, unsigned char>& code_map,
    std::string& error_message
) {
    std::ifstream input(compressed_path, std::ios::binary);
    if (!input) {
        error_message = "Unable to open compressed file.";
        return false;
    }

    char magic[4];
    input.read(magic, 4);
    if (!input || std::strncmp(magic, "HUFF", 4) != 0) {
        error_message = "Invalid compressed file format.";
        return false;
    }

    unsigned char version;
    input.read(reinterpret_cast<char*>(&version), 1);
    if (!input || version != 1) {
        error_message = "Unsupported compressed file version.";
        return false;
    }

    int unique_count = 0;
    int total_count = 0;
    input.read(reinterpret_cast<char*>(&unique_count), 4);
    input.read(reinterpret_cast<char*>(&total_count), 4);
    if (!input || unique_count < 0 || unique_count > 256 || total_count < 0) {
        error_message = "Invalid header metadata.";
        return false;
    }
    header_info.unique_symbol_count = unique_count;
    header_info.total_symbol_count = total_count;

    unsigned char ext_len = 0;
    input.read(reinterpret_cast<char*>(&ext_len), 1);
    if (!input || ext_len > 255) {
        error_message = "Invalid extension length in header.";
        return false;
    }
    std::string ext_string(ext_len, '\0');
    input.read(&ext_string[0], ext_len);
    if (!input) {
        error_message = "Failed to read original extension.";
        return false;
    }
    header_info.original_extension = ext_string;

    for (int i = 0; i < unique_count; ++i) {
        unsigned char symbol;
        input.read(reinterpret_cast<char*>(&symbol), 1);
        unsigned short code_len = 0;
        input.read(reinterpret_cast<char*>(&code_len), 2);
        if (!input || code_len == 0 || code_len > 1024) {
            error_message = "Invalid code entry in header.";
            return false;
        }
        std::string code(code_len, '\0');
        input.read(&code[0], code_len);
        if (!input) {
            error_message = "Failed to read Huffman code.";
            return false;
        }
        code_map[code] = symbol;
    }

    return true;
}

} // namespace huffcore
