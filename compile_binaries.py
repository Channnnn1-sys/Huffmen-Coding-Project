#!/usr/bin/env python3
"""#* Script to compile C++ Huffman compression binaries.
#* Works on Linux and macOS.
#! Windows users should use build.bat instead.
"""

import os
import subprocess
import sys
import platform
from pathlib import Path

def compile_binaries():
    """#! Compile huffcompress and huffdecompress binaries using g++.
    
    #* Returns 0 on success, 1 on failure
    """
    
    script_dir = Path(__file__).parent
    compressor_dir = script_dir / "compressor"
    
    print("=" * 70)
    print("Huffman Compressor Binary Compilation")
    print("=" * 70)
    print(f"Platform: {platform.system()}")
    print(f"Python: {platform.python_version()}")
    print(f"Script directory: {script_dir}")
    print(f"Compressor directory: {compressor_dir}")
    print()
    
    #! Platform check - abort on Windows
    if platform.system() == "Windows":
        print("ERROR: This script is for Linux/macOS only.")
        print("For Windows, use: build.bat")
        sys.exit(1)
    
    #! Verify compressor directory exists
    if not compressor_dir.exists():
        print(f"ERROR: Compressor directory not found: {compressor_dir}")
        sys.exit(1)
    
    #* Map source files to target binaries
    source_files = {
        "huffcompress.cpp": "huffcompress",
        "huffdecompress.cpp": "huffdecompress",
    }
    
    os.chdir(compressor_dir)
    print(f"Changed to: {os.getcwd()}")
    print()
    
    all_success = True
    
    for source, target in source_files.items():
        source_path = compressor_dir / source
        target_path = compressor_dir / target
        
        #! Check source file exists
        if not source_path.exists():
            print(f"ERROR: Source file not found: {source_path}")
            all_success = False
            continue
        
        print(f"Compiling {source}...")
        print(f"  Command: g++ -O2 -o {target} {source}")
        
        try:
            #* Run g++ compiler with optimization flags
            result = subprocess.run(
                ["g++", "-O2", "-o", target, source],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            #! Check compilation success
            if result.returncode == 0:
                if target_path.exists():
                    size = target_path.stat().st_size
                    print(f"  ✓ Success: {target} ({size} bytes)")
                else:
                    print(f"  ERROR: Output file not created")
                    all_success = False
            else:
                print(f"  ERROR: Compilation failed")
                if result.stdout:
                    print(f"  Stdout: {result.stdout}")
                if result.stderr:
                    print(f"  Stderr: {result.stderr}")
                all_success = False
        
        except subprocess.TimeoutExpired:
            print(f"  ERROR: Compilation timeout")
            all_success = False
        except Exception as e:
            print(f"  ERROR: {e}")
            all_success = False
        
        print()
    
    print("=" * 70)
    
    if all_success:
        print("✓ All binaries compiled successfully!")
        
        #* List generated binaries
        print("\nGenerated binaries:")
        for binary in ["huffcompress", "huffdecompress"]:
            binary_path = compressor_dir / binary
            if binary_path.exists():
                size = binary_path.stat().st_size
                mode = oct(binary_path.stat().st_mode)
                print(f"  - {binary} ({size} bytes, permissions: {mode})")
        
        return 0
    else:
        print("ERROR: Failed to compile all binaries")
        return 1

if __name__ == "__main__":
    sys.exit(compile_binaries())
