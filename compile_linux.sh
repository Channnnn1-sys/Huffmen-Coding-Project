#!/bin/bash
# Compile Huffman binaries for Linux

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
COMPRESSOR_DIR="$SCRIPT_DIR/compressor"

echo "=============================================================="
echo "Huffman Compressor Binary Compilation"
echo "=============================================================="
echo "Platform: $(uname -s)"
echo "Script directory: $SCRIPT_DIR"
echo "Compressor directory: $COMPRESSOR_DIR"
echo

# Ensure compressor directory exists
mkdir -p "$COMPRESSOR_DIR"

# Change to compressor directory
cd "$COMPRESSOR_DIR"

# Verify source files exist
if [ ! -f "huffcompress.cpp" ]; then
    echo "ERROR: huffcompress.cpp not found in $COMPRESSOR_DIR"
    exit 1
fi

if [ ! -f "huffdecompress.cpp" ]; then
    echo "ERROR: huffdecompress.cpp not found in $COMPRESSOR_DIR"
    exit 1
fi

# Link each executable against all shared implementation files in compressor/core.
# The linker errors happened because the project was refactored into multiple
# .cpp modules, but Render only compiled the main translation units.
# Compilation turns .cpp into object code; linking resolves all symbols across files.

echo "Compiling huffcompress..."
g++ -O3 -std=c++17 -o huffcompress huffcompress.cpp core/*.cpp -I.
if [ $? -eq 0 ]; then
    echo "✓ huffcompress compiled successfully"
else
    echo "✗ huffcompress compilation failed"
    exit 1
fi

echo
echo "Compiling huffdecompress..."
g++ -O3 -std=c++17 -o huffdecompress huffdecompress.cpp core/*.cpp -I.
if [ $? -eq 0 ]; then
    echo "✓ huffdecompress compiled successfully"
else
    echo "✗ huffdecompress compilation failed"
    exit 1
fi

echo
echo "Setting executable permissions..."
chmod +x huffcompress huffdecompress
echo "✓ Permissions set"

echo
echo "=============================================================="
echo "Listing compiled binaries:"
ls -lh huffcompress huffdecompress

echo
echo "✓ All binaries compiled successfully!"
