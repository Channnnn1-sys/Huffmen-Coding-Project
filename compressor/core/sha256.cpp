#include "sha256.h"
#include <array>
#include <cstdint>
#include <iomanip>
#include <sstream>

namespace huffcore {

namespace {

inline uint32_t rotate_right(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32 - n));
}

inline uint32_t choose(uint32_t e, uint32_t f, uint32_t g) {
    return (e & f) ^ (~e & g);
}

inline uint32_t majority(uint32_t a, uint32_t b, uint32_t c) {
    return (a & b) ^ (a & c) ^ (b & c);
}

inline uint32_t sigma0(uint32_t x) {
    return rotate_right(x, 2) ^ rotate_right(x, 13) ^ rotate_right(x, 22);
}

inline uint32_t sigma1(uint32_t x) {
    return rotate_right(x, 6) ^ rotate_right(x, 11) ^ rotate_right(x, 25);
}

inline uint32_t lower_sigma0(uint32_t x) {
    return rotate_right(x, 7) ^ rotate_right(x, 18) ^ (x >> 3);
}

inline uint32_t lower_sigma1(uint32_t x) {
    return rotate_right(x, 17) ^ rotate_right(x, 19) ^ (x >> 10);
}

const std::array<uint32_t, 64> k = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
    0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
    0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
    0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
    0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
    0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

} // namespace

std::string sha256_hex_buffer(const std::vector<unsigned char>& data) {
    std::array<uint32_t, 8> hash = {
        0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
        0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
    };

    std::vector<unsigned char> padded(data.begin(), data.end());
    const uint64_t bit_length = static_cast<uint64_t>(padded.size()) * 8ull;
    padded.push_back(0x80);
    while ((padded.size() % 64) != 56) {
        padded.push_back(0x00);
    }

    for (int i = 7; i >= 0; --i) {
        padded.push_back(static_cast<unsigned char>((bit_length >> (i * 8)) & 0xffu));
    }

    std::array<uint32_t, 64> w;
    for (size_t block_offset = 0; block_offset < padded.size(); block_offset += 64) {
        for (size_t t = 0; t < 16; ++t) {
            size_t index = block_offset + t * 4;
            w[t] = (static_cast<uint32_t>(padded[index]) << 24)
                 | (static_cast<uint32_t>(padded[index + 1]) << 16)
                 | (static_cast<uint32_t>(padded[index + 2]) << 8)
                 | (static_cast<uint32_t>(padded[index + 3]));
        }
        for (size_t t = 16; t < 64; ++t) {
            w[t] = lower_sigma1(w[t - 2]) + w[t - 7] + lower_sigma0(w[t - 15]) + w[t - 16];
        }

        uint32_t a = hash[0];
        uint32_t b = hash[1];
        uint32_t c = hash[2];
        uint32_t d = hash[3];
        uint32_t e = hash[4];
        uint32_t f = hash[5];
        uint32_t g = hash[6];
        uint32_t h = hash[7];

        for (size_t t = 0; t < 64; ++t) {
            const uint32_t temp1 = h + sigma1(e) + choose(e, f, g) + k[t] + w[t];
            const uint32_t temp2 = sigma0(a) + majority(a, b, c);
            h = g;
            g = f;
            f = e;
            e = d + temp1;
            d = c;
            c = b;
            b = a;
            a = temp1 + temp2;
        }

        hash[0] += a;
        hash[1] += b;
        hash[2] += c;
        hash[3] += d;
        hash[4] += e;
        hash[5] += f;
        hash[6] += g;
        hash[7] += h;
    }

    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (uint32_t value : hash) {
        output << std::setw(8) << value;
    }
    return output.str();
}

} // namespace huffcore
