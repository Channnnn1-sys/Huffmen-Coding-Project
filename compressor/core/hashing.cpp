#include "hashing.h"
#include "sha256.h"
#include <fstream>

namespace huffcore {

std::string sha256_hex(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return std::string();
    }

    std::vector<unsigned char> buffer;
    const size_t chunk_size = 8192;
    std::vector<unsigned char> chunk(chunk_size);

    while (input.read(reinterpret_cast<char*>(chunk.data()), static_cast<std::streamsize>(chunk.size())) || input.gcount() > 0) {
        buffer.insert(buffer.end(), chunk.begin(), chunk.begin() + input.gcount());
    }

    return sha256_hex_buffer(buffer);
}

} // namespace huffcore
