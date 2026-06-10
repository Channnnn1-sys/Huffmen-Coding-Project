#include <bits/stdc++.h>
#include <iomanip>
#include "core/file_utils.h"
#include "core/huffman_tree.h"
#include "core/metadata.h"
#include "core/report_generator.h"
#include "core/entropy.h"
using namespace std;
using namespace huffcore;

//* ============================================================================
//* HUFFMAN TREE DATA STRUCTURES
//* ============================================================================

struct Node {
    unsigned char character;
    size_t freq;
    Node* left;
    Node* right;
    //! Leaf node constructor for individual characters
    Node(unsigned char c, size_t f) : character(c), freq(f), left(nullptr), right(nullptr) {}
    //! Internal node constructor for merged nodes
    Node(size_t f, Node* l, Node* r) : character(0), freq(f), left(l), right(r) {}
};

//* Priority queue comparator - min heap by frequency
struct Compare {
    bool operator()(const Node* a, const Node* b) const {
        return a->freq > b->freq;
    }
};

//* Build Huffman tree by repeatedly merging lowest-frequency nodes
Node* buildHuffmanTree(priority_queue<Node*, vector<Node*>, Compare>& pq) {
    while (pq.size() > 1) {
        Node* left = pq.top(); pq.pop();
        Node* right = pq.top(); pq.pop();
        //* Create parent with combined frequency
        Node* merged = new Node(left->freq + right->freq, left, right);
        pq.push(merged);
    }
    return pq.top();
}

//* Traverse tree and assign binary codes to each character
void buildCodes(Node* node, const string& prefix, array<string, 256>& codes) {
    if (!node) return;
    //! Leaf node - store the binary code
    if (!node->left && !node->right) {
        codes[node->character] = prefix.empty() ? "0" : prefix;
        return;
    }
    //* Recursively traverse: left=0, right=1
    buildCodes(node->left, prefix + '0', codes);
    buildCodes(node->right, prefix + '1', codes);
}

//* Write compressed file header with codes and metadata
void writeHeader(ofstream& output, const array<string, 256>& codes, const vector<bool>& used, const string& extension, size_t symbol_count, size_t total_chars) {
    //* Magic number to identify HUFF format
    const char magic[4] = {'H', 'U', 'F', 'F'};
    output.write(magic, 4);

    //! Version byte for forward compatibility
    unsigned char version = 1;
    output.write(reinterpret_cast<const char*>(&version), 1);

    //* Number of unique symbols in file
    int code_count = static_cast<int>(symbol_count);
    output.write(reinterpret_cast<const char*>(&code_count), 4);

    //* Total character count (for decompression verification)
    int total_chars_int = static_cast<int>(total_chars);
    output.write(reinterpret_cast<const char*>(&total_chars_int), 4);

    //* Original file extension
    unsigned char ext_len = static_cast<unsigned char>(extension.size());
    output.write(reinterpret_cast<const char*>(&ext_len), 1);
    output.write(extension.c_str(), ext_len);

    //* Huffman code table: symbol -> code mapping
    for (size_t byte = 0; byte < codes.size(); ++byte) {
        if (!used[byte]) continue;
        unsigned char symbol = static_cast<unsigned char>(byte);
        output.write(reinterpret_cast<const char*>(&symbol), 1);

        const string& code = codes[byte];
        unsigned short code_len = static_cast<unsigned short>(code.size());
        output.write(reinterpret_cast<const char*>(&code_len), 2);
        output.write(code.c_str(), code_len);
    }
}

//* Encode file content using Huffman codes, packing bits efficiently
void encodeFile(ifstream& source, ofstream& output, const array<string, 256>& codes) {
    unsigned char buffer = 0;
    int bit_count = 0;
    const size_t block_size = 8192;
    vector<char> block(block_size);

    while (source.read(block.data(), static_cast<streamsize>(block.size())) || source.gcount() > 0) {
        streamsize bytes_read = source.gcount();
        for (streamsize i = 0; i < bytes_read; ++i) {
            unsigned char symbol = static_cast<unsigned char>(block[i]);
            const string& code = codes[symbol];
            //! Process each bit of the Huffman code
            for (char bit : code) {
                buffer = static_cast<unsigned char>((buffer << 1) | (bit - '0'));
                ++bit_count;
                //! Write full byte when buffer is complete
                if (bit_count == 8) {
                    output.write(reinterpret_cast<const char*>(&buffer), 1);
                    buffer = 0;
                    bit_count = 0;
                }
            }
        }
    }

    //! Pad and write remaining bits
    if (bit_count > 0) {
        buffer <<= (8 - bit_count);
        output.write(reinterpret_cast<const char*>(&buffer), 1);
    }
}

int main(int argc, char* argv[]) {
    //! Validate input arguments
    if (argc < 2) {
        cerr << "No input file provided" << endl;
        return 1;
    }

    const string input_path = argv[1];
    array<size_t, 256> frequency = {};
    size_t unique_symbols = 0;
    size_t total_bytes = 0;

    //! Open input file and read it
    ifstream input_file(input_path, ios::binary);
    if (!input_file.is_open()) {
        cerr << "Error: Unable to open input file for reading: " << input_path << endl;
        return 1;
    }

    //* First pass: count byte frequencies
    const size_t read_block = 65536;
    vector<char> read_buffer(read_block);
    while (input_file.read(read_buffer.data(), static_cast<streamsize>(read_buffer.size())) || input_file.gcount() > 0) {
        streamsize bytes_read = input_file.gcount();
        for (streamsize i = 0; i < bytes_read; ++i) {
            unsigned char symbol = static_cast<unsigned char>(read_buffer[i]);
            if (frequency[symbol] == 0) {
                ++unique_symbols;
            }
            ++frequency[symbol];
            ++total_bytes;
        }
    }

    //! Check for empty files
    if (total_bytes == 0) {
        cerr << "Error: Empty file or unable to read file" << endl;
        return 1;
    }

    //* Build Huffman tree from frequencies
    priority_queue<Node*, vector<Node*>, Compare> pq;
    vector<bool> symbol_used(256, false);
    for (size_t i = 0; i < frequency.size(); ++i) {
        if (frequency[i] > 0) {
            pq.push(new Node(static_cast<unsigned char>(i), frequency[i]));
            symbol_used[i] = true;
        }
    }

    //* Generate Huffman codes
    Node* root = buildHuffmanTree(pq);
    array<string, 256> codes_array;
    buildCodes(root, string(), codes_array);

    //* Prepare output filename
    size_t ext_pos = input_path.find_last_of('.');
    string base_name = (ext_pos == string::npos) ? input_path : input_path.substr(0, ext_pos);
    string extension = (ext_pos == string::npos) ? string() : input_path.substr(ext_pos);
    string output_path = base_name + "-compressed.bin";

    //! Create output file
    ofstream output_file(output_path, ios::binary);
    if (!output_file.is_open()) {
        cerr << "Error: Cannot create output file" << endl;
        return 1;
    }

    //* Write header and encode file
    writeHeader(output_file, codes_array, symbol_used, extension, static_cast<size_t>(unique_symbols), total_bytes);
    input_file.clear();
    input_file.seekg(0, ios::beg);
    encodeFile(input_file, output_file, codes_array);
    input_file.close();
    output_file.close();

    //* Calculate and persist compression statistics (metadata and report JSON)
    // Prepare frequency vector for report
    vector<size_t> frequencies(256);
    for (size_t i = 0; i < 256; ++i) frequencies[i] = frequency[i];

    // Build codes using helper to get code lengths
    auto codes = build_huffman_codes(frequencies);
    auto code_lengths = build_code_lengths(codes);

    // Compute entropy sample (use first 100KB)
    vector<unsigned char> sample = read_file_bytes(input_path, 100 * 1024);
    double entropy_value = shannon_entropy(sample);

    // Generate compression report
    CompressionReport report = generate_compression_report(input_path, output_path, code_lengths, frequencies, entropy_value);

    // Write metadata.json and compression_report.json next to output
    fs::path meta_path = fs::path(output_path).parent_path() / (fs::path(output_path).stem().string() + "-metadata.json");
    fs::path report_path = fs::path(output_path).parent_path() / (fs::path(output_path).stem().string() + "-compression_report.json");

    // metadata JSON (basic fields)
    string metadata_json = create_metadata_json("huffman", fs::path(input_path).filename().string(), fs::path(output_path).filename().string(), report.original_size, report.compressed_size, report.sha256, current_timestamp());
    ofstream meta_out(meta_path);
    if (meta_out) meta_out << metadata_json;
    meta_out.close();

    // detailed report JSON
    string report_json = report_to_json(report);
    ofstream report_out(report_path);
    if (report_out) report_out << report_json;
    report_out.close();

    cout << "Compression complete" << endl;
    return 0;
}
