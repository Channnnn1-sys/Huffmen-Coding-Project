#include <bits/stdc++.h>
#include <iomanip>
using namespace std;

struct Node {
    unsigned char character;
    size_t freq;
    Node* left;
    Node* right;
    Node(unsigned char c, size_t f) : character(c), freq(f), left(nullptr), right(nullptr) {}
    Node(size_t f, Node* l, Node* r) : character(0), freq(f), left(l), right(r) {}
};

struct Compare {
    bool operator()(const Node* a, const Node* b) const {
        return a->freq > b->freq;
    }
};

Node* buildHuffmanTree(priority_queue<Node*, vector<Node*>, Compare>& pq) {
    while (pq.size() > 1) {
        Node* left = pq.top(); pq.pop();
        Node* right = pq.top(); pq.pop();
        Node* merged = new Node(left->freq + right->freq, left, right);
        pq.push(merged);
    }
    return pq.top();
}

void buildCodes(Node* node, const string& prefix, array<string, 256>& codes) {
    if (!node) return;
    if (!node->left && !node->right) {
        codes[node->character] = prefix.empty() ? "0" : prefix;
        return;
    }
    buildCodes(node->left, prefix + '0', codes);
    buildCodes(node->right, prefix + '1', codes);
}

void writeHeader(ofstream& output, const array<string, 256>& codes, const vector<bool>& used, const string& extension, size_t symbol_count, size_t total_chars) {
    const char magic[4] = {'H', 'U', 'F', 'F'};
    output.write(magic, 4);

    unsigned char version = 1;
    output.write(reinterpret_cast<const char*>(&version), 1);

    int code_count = static_cast<int>(symbol_count);
    output.write(reinterpret_cast<const char*>(&code_count), 4);

    int total_chars_int = static_cast<int>(total_chars);
    output.write(reinterpret_cast<const char*>(&total_chars_int), 4);

    unsigned char ext_len = static_cast<unsigned char>(extension.size());
    output.write(reinterpret_cast<const char*>(&ext_len), 1);
    output.write(extension.c_str(), ext_len);

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
            for (char bit : code) {
                buffer = static_cast<unsigned char>((buffer << 1) | (bit - '0'));
                ++bit_count;
                if (bit_count == 8) {
                    output.write(reinterpret_cast<const char*>(&buffer), 1);
                    buffer = 0;
                    bit_count = 0;
                }
            }
        }
    }

    if (bit_count > 0) {
        buffer <<= (8 - bit_count);
        output.write(reinterpret_cast<const char*>(&buffer), 1);
    }
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        cerr << "No input file provided" << endl;
        return 1;
    }

    const string input_path = argv[1];
    array<size_t, 256> frequency = {};
    size_t unique_symbols = 0;
    size_t total_bytes = 0;

    ifstream input_file(input_path, ios::binary);
    if (!input_file.is_open()) {
        cerr << "Error: Unable to open input file for reading: " << input_path << endl;
        return 1;
    }

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

    if (total_bytes == 0) {
        cerr << "Error: Empty file or unable to read file" << endl;
        return 1;
    }

    priority_queue<Node*, vector<Node*>, Compare> pq;
    vector<bool> symbol_used(256, false);
    for (size_t i = 0; i < frequency.size(); ++i) {
        if (frequency[i] > 0) {
            pq.push(new Node(static_cast<unsigned char>(i), frequency[i]));
            symbol_used[i] = true;
        }
    }

    Node* root = buildHuffmanTree(pq);
    array<string, 256> codes;
    buildCodes(root, string(), codes);

    size_t ext_pos = input_path.find_last_of('.');
    string base_name = (ext_pos == string::npos) ? input_path : input_path.substr(0, ext_pos);
    string extension = (ext_pos == string::npos) ? string() : input_path.substr(ext_pos);
    string output_path = base_name + "-compressed.bin";

    ofstream output_file(output_path, ios::binary);
    if (!output_file.is_open()) {
        cerr << "Error: Cannot create output file" << endl;
        return 1;
    }

    writeHeader(output_file, codes, symbol_used, extension, static_cast<size_t>(unique_symbols), total_bytes);
    input_file.clear();
    input_file.seekg(0, ios::beg);
    encodeFile(input_file, output_file, codes);
    input_file.close();
    output_file.close();

    ifstream original_file(input_path, ios::binary | ios::ate);
    size_t original_size = original_file.tellg();
    original_file.close();
    ifstream compressed_file(output_path, ios::binary | ios::ate);
    size_t compressed_size = compressed_file.tellg();
    compressed_file.close();

    double ratio = (original_size > 0) ? (static_cast<double>(compressed_size) / original_size) * 100.0 : 0.0;
    cout << "Compression complete" << endl;
    cout << "Original size: " << original_size << " bytes" << endl;
    cout << "Compressed size: " << compressed_size << " bytes" << endl;
    cout << "Compression ratio: " << fixed << setprecision(2) << ratio << "%" << endl;

    return 0;
}
