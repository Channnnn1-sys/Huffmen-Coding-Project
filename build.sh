#!/bin/bash

# Build script for Huffman compression binaries
# Works on Linux/macOS. For Windows, use build.bat

set -e  # Exit on error

echo "Building Huffman compression binaries..."
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPRESSOR_DIR="$SCRIPT_DIR/compressor"

if [ ! -d "$COMPRESSOR_DIR" ]; then
    echo "Error: compressor directory not found at $COMPRESSOR_DIR"
    exit 1
fi

echo "Compiling huffcompress..."
g++ -O3 -std=c++17 -o "$COMPRESSOR_DIR/huffcompress" "$COMPRESSOR_DIR/huffcompress.cpp" "$COMPRESSOR_DIR/core"/*.cpp -I"$COMPRESSOR_DIR"

echo "Compiling huffdecompress..."
g++ -O3 -std=c++17 -o "$COMPRESSOR_DIR/huffdecompress" "$COMPRESSOR_DIR/huffdecompress.cpp" "$COMPRESSOR_DIR/core"/*.cpp -I"$COMPRESSOR_DIR"

echo "=========================================="
echo "Build successful!"
echo "Binaries created:"
echo "  - $COMPRESSOR_DIR/huffcompress"
echo "  - $COMPRESSOR_DIR/huffdecompress"
