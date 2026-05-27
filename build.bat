@echo off
REM Build script for Huffman compression binaries on Windows
REM Requires g++ to be installed (e.g., via MSYS2)

echo Building Huffman compression binaries...
echo ==========================================

setlocal enabledelayedexpansion

REM Find the compressor directory
set SCRIPT_DIR=%~dp0
set COMPRESSOR_DIR=%SCRIPT_DIR%compressor

if not exist "%COMPRESSOR_DIR%" (
    echo Error: compressor directory not found at %COMPRESSOR_DIR%
    exit /b 1
)

echo Compiling huffcompress.exe...
g++ -O2 -o "%COMPRESSOR_DIR%\huffcompress.exe" "%COMPRESSOR_DIR%\huffcompress.cpp"

if !errorlevel! neq 0 (
    echo Error compiling huffcompress.cpp
    exit /b 1
)

echo Compiling huffdecompress.exe...
g++ -O2 -o "%COMPRESSOR_DIR%\huffdecompress.exe" "%COMPRESSOR_DIR%\huffdecompress.cpp"

if !errorlevel! neq 0 (
    echo Error compiling huffdecompress.cpp
    exit /b 1
)

echo ==========================================
echo Build successful!
echo Binaries created:
echo   - %COMPRESSOR_DIR%\huffcompress.exe
echo   - %COMPRESSOR_DIR%\huffdecompress.exe
