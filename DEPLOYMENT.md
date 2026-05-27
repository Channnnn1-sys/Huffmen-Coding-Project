# Cloud Deployment Guide - Huffman Compression App

## Overview

This Flask application has been refactored for cloud deployment on Render and other Linux-based platforms. The app now uses a **stateless processing model** where all temporary files are cleaned up after each operation.

## Key Changes for Cloud Readiness

### 1. **Stateless File Processing**
- **Before**: Files stored permanently in `uploads/`, `downloads/`, `temp/` directories
- **After**: Uses Python's `tempfile.TemporaryDirectory()` for session-scoped temporary files
- **Benefit**: No persistent file storage on server; automatic cleanup after processing

### 2. **Platform-Agnostic Binary Handling**
- **Before**: Hardcoded `.exe` files for Windows only
- **After**: Dynamically detects OS and uses appropriate binary:
  - Windows: `huffcompress.exe`, `huffdecompress.exe`
  - Linux/macOS: `huffcompress`, `huffdecompress`
- **Benefit**: Single codebase works on Windows, Linux, and macOS

### 3. **Client-Side Download Streaming**
- **Before**: Files stored on server disk after processing
- **After**: Files returned as base64-encoded data in JSON response
- **Client**: Browser decodes and downloads directly via blob URL
- **Benefit**: No server-side file persistence, reduced I/O, instant cleanup

### 4. **Production-Ready Subprocess Execution**
- Proper timeout handling with 30-second default
- Graceful error messages for missing binaries
- Cross-platform subprocess compatibility
- Full error logging for debugging

### 5. **Render/Linux Compatibility**
- `render.yaml` configured with build and start commands
- Automated C++ binary compilation during build phase
- Environment-aware logging (Linux file paths, binary names)
- gunicorn with 4 workers for production

## Deployment Instructions

### Local Development (Windows)

1. **Build C++ binaries:**
   ```bash
   build.bat
   ```
   Or manually:
   ```bash
   g++ -O2 -o compressor/huffcompress.exe compressor/huffcompress.cpp
   g++ -O2 -o compressor/huffdecompress.exe compressor/huffdecompress.cpp
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run development server:**
   ```bash
   python main.py
   ```
   Visit: `http://localhost:5000`

### Local Development (Linux/macOS)

1. **Build C++ binaries:**
   ```bash
   chmod +x build.sh
   ./build.sh
   ```
   Or manually:
   ```bash
   g++ -O2 -o compressor/huffcompress compressor/huffcompress.cpp
   g++ -O2 -o compressor/huffdecompress compressor/huffdecompress.cpp
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run development server:**
   ```bash
   python main.py
   ```
   Visit: `http://localhost:5000`

### Production Deployment (Render)

1. **Connect repository to Render:**
   - Go to [Render Dashboard](https://dashboard.render.com)
   - Click "New" → "Web Service"
   - Connect your GitHub repository
   - Render will detect `render.yaml` automatically

2. **Automatic build & deployment:**
   - Render will run: `g++ -O2 compressor/huffcompress.cpp -o compressor/huffcompress && g++ -O2 compressor/huffdecompress.cpp -o compressor/huffdecompress && pip install -r requirements.txt`
   - Then start: `gunicorn -w 4 -b 0.0.0.0:8000 main:app`

3. **Monitor deployment:**
   - Check build logs in Render dashboard
   - Verify both C++ binaries compile successfully
   - Confirm app starts without errors

### Environment Variables

Set these in your Render dashboard under "Environment":

```
SECRET_KEY=your-secret-key-here
PYTHON_VERSION=3.11
```

## Architecture

### Request Flow

```
User Upload
    ↓
[POST /compress or /decompress]
    ↓
Create TemporaryDirectory
    ↓
Save file to temp directory
    ↓
Execute C++ binary (subprocess)
    ↓
Read output file into memory
    ↓
Base64 encode result
    ↓
Return JSON response with encoded data
    ↓
Temporary directory auto-deleted
    ↓
Browser decodes base64 and downloads file
```

### File Lifecycle

1. **Upload**: Temp file created in memory-managed temporary directory
2. **Processing**: C++ binary reads/writes in same temporary directory
3. **Response**: Output file read into memory and base64 encoded
4. **Cleanup**: Temporary directory completely removed (automatic)
5. **Client**: Browser handles final download from memory

## Performance Considerations

### Memory Usage
- **Upload limit**: 100MB (configurable in `main.py`)
- **Temporary files**: Stored in OS temp directory (e.g., `/tmp` on Linux)
- **Base64 encoding**: ~33% overhead (handled client-side after download)

### CPU Optimization
- C++ binaries compiled with `-O2` flag for optimization
- Huffman algorithm: O(n log n) complexity
- Multi-worker gunicorn: 4 workers for concurrent requests

### Disk Usage
- **No persistent storage** on server
- All temp files cleaned up immediately
- No accumulation of processed files

## Troubleshooting

### "Compressor binary not found"

**On Render:**
- Check build logs for C++ compilation errors
- Ensure g++ is available (included in standard Render Python runtime)
- Verify file paths in error message match expected locations

**Locally:**
- Run `build.sh` (Linux) or `build.bat` (Windows)
- Check that `.exe` files (Windows) or binaries (Linux) are created
- Verify file paths: `./compressor/huffcompress[.exe]`

### "Process timeout"

- Default timeout: 30 seconds
- For larger files, may need adjustment in `run_compressor()` function
- Check Render logs for subprocess errors

### "Decompressed output file not found"

- Ensure uploaded `.bin` file is validly compressed
- Original file format must be embedded in the `.bin` header
- Check for corrupted files

### High Memory Usage

- 100MB upload limit should prevent OOM
- If needed, reduce `MAX_CONTENT_LENGTH` in `main.py`
- Monitor temp directory during heavy usage

## Testing

### Test Compression
```bash
curl -X POST http://localhost:5000/compress \
  -F "files=@test_file.txt"
```

### Test Decompression
```bash
curl -X POST http://localhost:5000/decompress \
  -F "files=@test_file-compressed.bin"
```

### Response Format
```json
{
  "job_id": "abc12345",
  "results": [
    {
      "filename": "test.txt",
      "success": true,
      "compressed_filename": "test-compressed.bin",
      "original_size": 1024,
      "compressed_size": 512,
      "compression_ratio": 50.0,
      "saved_bytes": 512,
      "data_b64": "base64_encoded_binary_data_here"
    }
  ],
  "timestamp": "2024-05-10T10:30:00.123456"
}
```

## Security

### File Handling
- All filenames sanitized with `secure_filename()`
- Max upload size enforced (100MB)
- Temp files isolated in system temp directory
- No path traversal vulnerabilities

### Process Execution
- Subprocess executed with `capture_output=True`
- Timeout enforced to prevent hanging
- stderr captured for error diagnostics

## Migration from Old Version

If upgrading from the pre-refactored version:

1. **Old directories can be safely deleted:**
   - `uploads/` - no longer used
   - `downloads/` - no longer used
   - `temp/` - no longer used
   - `downloads/jobs/` - no longer used

2. **Environment changes:**
   - No `.env` file required for file storage
   - Jobs are no longer saved to disk

3. **API compatibility:**
   - `/compress` and `/decompress` endpoints return same JSON format
   - Download mechanism changed: use `data_b64` field instead of `/download/<filename>`
   - `/download/` endpoint removed

## Production Monitoring

### Logs to Watch

```bash
# Connection/request logs
curl https://your-app.render.com/

# Build process
# Check Render dashboard → Deploy logs

# Runtime errors
# Check Render dashboard → Logs
```

### Metrics to Monitor

- Response time: Should be <5s for typical files
- Error rate: Watch for subprocess failures
- CPU usage: gunicorn should load-balance across 4 workers
- Memory: Should stay stable (no accumulation)

## Next Steps

1. Deploy to Render
2. Test all features in production
3. Monitor logs and performance
4. Adjust gunicorn workers if needed
5. Consider adding file type restrictions beyond current whitelist

---

**Questions?** Review the refactored `main.py` for implementation details or check Flask/Render documentation.
