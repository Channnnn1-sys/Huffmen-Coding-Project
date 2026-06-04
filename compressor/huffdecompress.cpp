#include <bits/stdc++.h>
using namespace std;

//* ============================================================================
//* DECOMPRESSION: Extract Huffman codes from compressed file header
//* ============================================================================

bool extractcodes(
    int &noofchars,
    string &extension,
    ifstream &readfile,
    unordered_map<string, char> &m
) {
    //! Validate HUFF magic number
    char magic[4];
    readfile.read(magic, 4);
    if (!readfile || strncmp(magic, "HUFF", 4) != 0) {
        cerr << "Invalid compressed file format." << endl;
        return false;
    }

    //! Check version for compatibility
    unsigned char version;
    readfile.read(reinterpret_cast<char*>(&version), 1);
    if (!readfile || version != 1) {
        cerr << "Unsupported compressed file version." << endl;
        return false;
    }

    //* Read header metadata
    int x;  //! Number of unique symbols
    readfile.read(reinterpret_cast<char*>(&x), 4);
    readfile.read(reinterpret_cast<char*>(&noofchars), 4);  //! Total character count
    if (!readfile || x < 0 || x > 256 || noofchars < 0) {
        cerr << "Invalid compressed file header." << endl;
        return false;
    }

    //! Read original file extension
    unsigned char ext_len;
    readfile.read(reinterpret_cast<char*>(&ext_len), 1);
    if (!readfile || ext_len > 255) {
        cerr << "Invalid extension length in compressed file." << endl;
        return false;
    }

    string ext_buffer(ext_len, '\0');
    readfile.read(&ext_buffer[0], ext_len);
    if (!readfile) {
        cerr << "Failed to read file extension from compressed file." << endl;
        return false;
    }
    extension = ext_buffer;

    //* Extract Huffman code table (binary code -> character mapping)
    for (int i = 0; i < x; i++) {
        unsigned char ascii;
        readfile.read(reinterpret_cast<char*>(&ascii), 1);
        if (!readfile) {
            cerr << "Failed to read code entry from compressed file." << endl;
            return false;
        }

        unsigned short key_len;
        readfile.read(reinterpret_cast<char*>(&key_len), 2);
        if (!readfile || key_len > 1024) {
            cerr << "Invalid code length in compressed file." << endl;
            return false;
        }

        string key(key_len, '\0');
        readfile.read(&key[0], key_len);
        if (!readfile) {
            cerr << "Failed to read Huffman code from compressed file." << endl;
            return false;
        }

        m[key] = static_cast<char>(ascii);
    }

    return true;
}

//* Convert single byte to binary string representation
string dectobin(unsigned char decimal) {
    string s = "";
    //! Extract each bit from MSB to LSB
    for (int i = 7; i >= 0; i--) {
        s += ((decimal >> i) & 1) ? "1" : "0";
    }
    return s;
}

//* Decode compressed file using Huffman code table
void extractfile(
    int &noofchars,
    ifstream &readfile,
    ofstream &newfile,
    unordered_map<string, char> &m
) {
    unsigned char p;
    string s = "";
    string current = "";
    int count = 0;

    //! Process each byte of compressed data
    while (readfile.read(reinterpret_cast<char*>(&p), 1)) {
        //! Convert byte to binary string
        s += dectobin(p);
        current = "";

        //* Try to match prefixes with Huffman codes
        for (char bit : s) {
            current += bit;

            //! When a code matches, write corresponding character
            if (m.find(current) != m.end()) {
                newfile.put(m[current]);
                count++;
                current = "";

                //! Stop when we've decompressed all characters
                if (count >= noofchars)
                    return;
            }
        }

        s = current;
    }

    //! Check for remaining bits that might form a valid code
    if (!current.empty() && m.find(current) != m.end()) {
        newfile.put(m[current]);
        count++;
    }

    //! Verify decompression completeness
    if (count != noofchars) {
        cerr << "Warning: Decompressed " << count << " characters, expected " << noofchars << endl;
    }
}

int main(int argc, char* argv[]) {
    //! Validate input arguments
    if (argc < 2) {
        cout << "No input file provided" << endl;
        return 1;
    }

    string file = argv[1];
    unordered_map<string, char> m;  //* Huffman code -> character mapping

    //! Open compressed input file
    ifstream readfile(file, ios::binary);
    if (!readfile.is_open()) {
        cerr << "Unable to open compressed file." << endl;
        return 1;
    }

    int noofchars;
    string extension;

    //! Extract codes from header
    if (!extractcodes(noofchars, extension, readfile, m)) {
        return 1;
    }

    //* Generate output filename
    size_t marker = file.rfind("-compressed.bin");
    string output;

    if (marker != string::npos) {
        output = file.substr(0, marker) + "-decompressed" + extension;
    } else {
        size_t dot = file.find_last_of('.');
        if (dot != string::npos) {
            output = file.substr(0, dot) + "-decompressed" + extension;
        } else {
            output = file + "-decompressed" + extension;
        }
    }
    
    //! Create output file
    ofstream newfile(output, ios::binary | ios::out);
    if (!newfile.is_open()) {
        cerr << "Error: Cannot create output file: " << output << endl;
        return 1;
    }

    //* Decode and write decompressed content
    extractfile(noofchars, readfile, newfile, m);

    newfile.close();
    readfile.close();

    cout << "Decompression complete" << endl;

    return 0;
}
