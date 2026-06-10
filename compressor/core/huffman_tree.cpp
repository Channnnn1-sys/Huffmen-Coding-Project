#include "huffman_tree.h"
#include <queue>
#include <vector>

namespace huffcore {

struct Node {
    unsigned char symbol;
    size_t frequency;
    Node* left;
    Node* right;
    Node(unsigned char symbol_, size_t frequency_) : symbol(symbol_), frequency(frequency_), left(nullptr), right(nullptr) {}
    Node(Node* left_, Node* right_) : symbol(0), frequency(left_->frequency + right_->frequency), left(left_), right(right_) {}
};

struct Compare {
    bool operator()(const Node* a, const Node* b) const {
        return a->frequency > b->frequency;
    }
};

void build_codes_recursive(Node* node, const std::string& prefix, std::unordered_map<unsigned char, std::string>& codes) {
    if (!node) {
        return;
    }
    if (!node->left && !node->right) {
        codes[node->symbol] = prefix.empty() ? "0" : prefix;
        return;
    }
    build_codes_recursive(node->left, prefix + "0", codes);
    build_codes_recursive(node->right, prefix + "1", codes);
}

std::unordered_map<unsigned char, std::string> build_huffman_codes(
    const std::vector<size_t>& frequencies
) {
    std::priority_queue<Node*, std::vector<Node*>, Compare> queue;
    for (unsigned int i = 0; i < frequencies.size(); ++i) {
        if (frequencies[i] > 0) {
            queue.push(new Node(static_cast<unsigned char>(i), frequencies[i]));
        }
    }
    if (queue.empty()) {
        return {};
    }
    while (queue.size() > 1) {
        Node* left = queue.top(); queue.pop();
        Node* right = queue.top(); queue.pop();
        queue.push(new Node(left, right));
    }
    Node* root = queue.top();
    std::unordered_map<unsigned char, std::string> codes;
    build_codes_recursive(root, "", codes);
    return codes;
}

std::unordered_map<unsigned char, unsigned int> build_code_lengths(
    const std::unordered_map<unsigned char, std::string>& codes
) {
    std::unordered_map<unsigned char, unsigned int> lengths;
    for (const auto& [symbol, code] : codes) {
        lengths[symbol] = static_cast<unsigned int>(code.size());
    }
    return lengths;
}

} // namespace huffcore
