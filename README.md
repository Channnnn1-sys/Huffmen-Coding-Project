# Huffman File Compression Web Application

A Flask-based web application that combines a Python backend with a C++ Huffman coding compressor to provide file compression and decompression via a simple web UI.

## Overview

This repository implements a stateless Flask service that uses an external C++ Huffman compressor/decompressor to process files in temporary session directories and return results to the browser as base64 payloads. It is designed for local development and cloud deployment (Render, generic Linux hosts).

### Features

- Compress and decompress files with a C++ Huffman engine
- Batch uploads (multiple files per request)
- Client-side download via base64 JSON responses (no persistent server storage)
- Office ZIP deep-scan analysis for text-heavy Office files
- Entropy analysis and compression statistics (ratio, top symbols, efficiency)
- Simple responsive UI (templates in `templates/`)

## Tech stack

- Python 3.8+ with Flask (web framework)
- C++ (Huffman compressor/decompressor in `compressor/`)
- HTML/CSS/JavaScript front end (templates + static assets)
- Gunicorn for production WSGI hosting
- Designed for Linux, macOS, and Windows

## Architecture

Requests are processed in a temporary session directory created with `tempfile.TemporaryDirectory()`. Uploaded files are saved there, the C++ binary is invoked in that directory, outputs are read into memory, base64-encoded and returned to the client. Temporary directories are removed automatically.

Key routes:

- `GET /` - Home (`templates/index.html`)
- `GET/POST /compress` - Compress files
- `GET/POST /decompress` - Decompress `.bin` files
- `GET /about` - About page
- `GET /debug` - Debug info (environment, binaries)

## Installation

1. Clone the repo and create a Python environment

```bash
git clone <repo>
cd File-Compression-Using-Huffman-Coding-Flask-App-main
python -m venv .venv
source .venv/bin/activate  # or .venv\\Scripts\\activate on Windows
pip install -r requirements.txt
```

2. Build C++ binaries

```bash
# Linux/macOS
./build.sh

# Windows
build.bat
```

3. Run locally

```bash
python main.py
```

For full deployment instructions see `DEPLOYMENT.md` and `QUICKSTART.md`.

## Usage

Open `http://localhost:5000` and use the web UI to compress or decompress files. Uploaded files are processed in a temporary session and returned as base64 payloads; the browser will trigger downloads.

API examples (curl):

```bash
# Compress
curl -X POST http://localhost:5000/compress -F "files=@myfile.txt"

# Decompress
curl -X POST http://localhost:5000/decompress -F "files=@myfile-compressed.bin"
```

## Project structure

Relevant files and folders:

```
main.py                # Flask application (entry point)
requirements.txt       # Python dependencies
compressor/            # C++ source and compiled binaries
templates/             # HTML templates (index, compress, decompress, about)
static/                # CSS and JS assets
build.sh / build.bat   # Platform build scripts for the C++ binaries
render.yaml            # Render deployment configuration
```

Configuration is primarily controlled in `main.py` (upload size, allowed extensions).

## Limitations

- Processing is currently sequential (no worker pool per request); large batches are processed file-by-file.
- Base64 payloads increase memory usage by ~33% while data is held in memory
- Large files (>~500MB) may cause memory or timeout issues depending on host

See `DEPLOYMENT.md` for deployment-specific considerations and tuning (timeouts, gunicorn worker count).

## Future improvements

- Add optional worker pool / parallel processing for batch jobs
- Stream large file transfers to avoid full in-memory base64 for very large files
- Add automated tests and CI (unit + integration) covering compress/decompress flows
- Provide a Dockerfile and containerized build image for consistent deployment
- Add monitoring, rate limiting and authentication for production deployments

## Credits

- Project implemented using Flask and a C++ Huffman compressor
- Third-party libraries: Flask, Werkzeug, Gunicorn

---

For more detailed deployment steps and troubleshooting see `DEPLOYMENT.md` and `QUICKSTART.md`.

## Usage Guide

### Compressing Files

1. Click the **"Compress Files"** button on the home page
2. Drag and drop files onto the upload box, or click to browse
3. Select one or more files (any file type supported)
4. Click **"Compress Files"**
5. View compression results (original size, compressed size, ratio, saved bytes)
6. Download the compressed `.bin` file

### Decompressing Files

1. Click the **"Decompress Files"** button on the home page
2. Drag and drop `.bin` files onto the upload box, or click to browse
3. Select one or more `.bin` files
4. Click **"Decompress Files"**
5. View decompression results
6. Download the restored original file

### Viewing Application Information

- **About Page**: Learn more about the project, team members, and technology stack
- **Theme Toggle**: Click the moon/sun icon to switch between dark and light modes
- **Navigation**: Use the top navigation bar to move between pages

## Technical Details

### File Format

The compressed file format includes a binary header:

```
[Magic: "HUFF"] [Version] [CharCount] [UniqueChars] [ExtLength] [Extension] [CodeTable] [EncodedData]
```

- **Magic**: 4-byte identifier "HUFF"
- **Version**: 1-byte version number
- **CharCount**: 4-byte count of characters in original file
- **UniqueChars**: 4-byte count of unique characters
- **ExtLength**: 1-byte length of original file extension
- **Extension**: Variable-length original file extension
- **CodeTable**: Huffman code mappings
- **EncodedData**: Actual compressed binary data

### Configuration

Key settings in `main.py`:

```python
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max upload
CLEANUP_TIMEOUT = 3600  # 1 hour in seconds
```

Modify these values as needed for your deployment.

### Environment Variables

You can set a custom secret key using:

```bash
set SECRET_KEY=your-secret-key-here  # Windows
export SECRET_KEY=your-secret-key-here  # Linux/macOS
```

If not set, the application defaults to a development key.

## API Endpoints

### Web Routes

- `GET /` - Home page
- `GET /compress` - Compression page
- `POST /compress` - Compress uploaded files
- `GET /decompress` - Decompression page
- `POST /decompress` - Decompress uploaded files
- `GET /download/<filename>` - Download processed file
- `GET /about` - About page

### JSON Response Format

**Successful Compression:**

```json
{
  "job_id": "a1b2c3d4",
  "results": [
    {
      "filename": "document.txt",
      "success": true,
      "compressed_filename": "document-compressed.bin",
      "original_size": 10240,
      "compressed_size": 6144,
      "compression_ratio": 60.0,
      "saved_bytes": 4096
    }
  ],
  "timestamp": "2024-01-15T10:30:00.000000"
}
```

**Error Response:**

```json
{
  "job_id": "a1b2c3d4",
  "results": [
    {
      "filename": "document.txt",
      "success": false,
      "error": "File type not allowed"
    }
  ],
  "timestamp": "2024-01-15T10:30:00.000000"
}
```

## Troubleshooting

### C++ Executable Not Found

**Error**: `ERROR: huffcompress.exe not found!`

**Solution**: Rebuild the C++ files in the `compressor/` directory:

```bash
cd compressor
g++ -O2 -o huffcompress.exe huffcompress.cpp
g++ -O2 -o huffdecompress.exe huffdecompress.cpp
```

### Port Already in Use

**Error**: `Address already in use: ('127.0.0.1', 5000)`

**Solution**: The port 5000 is already in use. Either:
- Stop the process using port 5000
- Or modify `main.py` line: `app.run(..., port=5001)`

### File Upload Fails

**Issue**: Large files fail to upload

**Solution**: Check `MAX_CONTENT_LENGTH` in `main.py`. Default is 100MB. Increase if needed:

```python
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB
```

### Decompression Shows Warning

**Message**: `Warning: Decompressed X characters, expected Y`

**Cause**: Minor data integrity check. Usually still works correctly.

**Solution**: Verify the `.bin` file was created properly and wasn't corrupted.

### Dark Mode Not Saving

**Issue**: Theme preference not persistent across sessions

**Cause**: Browser localStorage might be disabled

**Solution**: Enable localStorage in browser settings (this is normal browser behavior)

## Performance Notes

- Compression speed depends on file size and content
- Large files (> 50MB) may take several seconds
- C++ implementation is optimized with O2 compiler flags
- Batch processing processes files sequentially (one at a time)

## Known Limitations

1. **Sequential Processing**: Files are compressed/decompressed one at a time, not in parallel
2. **Memory**: Large files (> 500MB) may cause memory issues
3. **Character Count**: Limited to files with up to 2^31 characters
4. **Binary Files**: Some binary formats may not compress well
5. **UTF-16 Encoding**: UTF-16 encoded files are treated as binary (less efficient compression)
6. **File Extensions**: Limited to 255 characters

## Security Considerations

- ✅ Uses `secure_filename()` for all uploaded files
- ✅ Validates file extensions on server side
- ✅ Automatic cleanup of temporary files after 1 hour
- ✅ Maximum upload size limit enforced
- ⚠️ **Not suitable for production** without additional security hardening
- ⚠️ Use environment variables for SECRET_KEY in production
- ⚠️ Consider adding rate limiting for production deployment
- ⚠️ Enable HTTPS for sensitive data transmission

## Development & Modification

### Adding File Types

To allow additional file extensions, modify `ALLOWED_EXTENSIONS` in `main.py`:

```python
ALLOWED_EXTENSIONS = {"txt", "pdf", "doc", "docx", "bin", "log", "csv", "json", "xml"}
```

### Changing Upload Directory

To change where files are uploaded, modify the path in `main.py`:

```python
UPLOADS_DIR = BASE_DIR / "my_custom_uploads"
```

### Modifying UI Theme

Update colors in `static/css/style.css`:

```css
/* Dark mode colors */
body { background: #0b1220; color: #e5e7eb; }

/* Light mode colors */
body.light-mode { background: #f8fafc; color: #1e293b; }

/* Accent color */
#para-1 { color: #38bdf8; }
```

## Building for Production

Before deploying to production:

1. Set a strong `SECRET_KEY`:
   ```bash
   export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
   ```

2. Change debug mode in `main.py`:
   ```python
   app.run(debug=False, host="0.0.0.0", port=5000)
   ```

3. Use a production WSGI server (e.g., Gunicorn, Waitress):
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 main:app
   ```

4. Add reverse proxy (Nginx, Apache) for security
5. Enable HTTPS with SSL certificates
6. Implement rate limiting
7. Add monitoring and logging

## License & Attribution

This is an educational project developed for learning purposes.

## Project Team

- **Nikko Madueño** - QA & Testing Specialist
- **Arman Christian Malgapo** - Lead Developer & Backend Systems Programmer
- **Paul Henrick Maquiniana** - Project Coordinator & Development Manager
- **Theo Masato Nakajima** - Technical Documentation & Research Specialist

## Frequently Asked Questions

**Q: Can I use this for production?**
A: Not without significant hardening. See "Building for Production" section.

**Q: What file types are supported?**
A: Any file type, but compression works best on text files. See `ALLOWED_EXTENSIONS`.

**Q: Can I modify the Huffman algorithm?**
A: Yes! The implementation is in `compressor/huffcompress.cpp` and `compressor/huffdecompress.cpp`.

**Q: How do I get better compression ratios?**
A: Huffman coding works best on files with repetitive patterns (text, logs, code).

**Q: Is there a maximum file size?**
A: Yes, limited to `MAX_CONTENT_LENGTH` (default 100MB) and available memory.

**Q: Can I deploy on cloud servers (AWS, Azure, Heroku)?**
A: Yes, but you'll need to cross-compile the C++ for the target platform.

## Support & Questions

For issues or questions:
1. Check the Troubleshooting section
2. Review code comments in `main.py`
3. Check browser console for JavaScript errors (F12)
4. Verify C++ executables are built correctly

## Changelog

### Version 1.0.0 (Refactored)

**Improvements:**
- ✅ Complete code reorganization
- ✅ Fixed repeated processing bugs
- ✅ Removed global state variables
- ✅ Proper Windows path handling with pathlib
- ✅ Replaced unsafe subprocess patterns
- ✅ Added proper error handling
- ✅ Fixed timeout handling
- ✅ Added automatic file cleanup
- ✅ Rewrote HTML templates with AJAX support
- ✅ Added responsive design
- ✅ Unified CSS with light/dark theme
- ✅ Multi-file upload for both compress and decompress
- ✅ Real-time result display
- ✅ Drag-and-drop on all upload pages

**Bugs Fixed:**
- Fixed infinite loops in file processing
- Fixed file polling issues
- Fixed route logic duplication
- Fixed missing Flask response handling
- Fixed global filename state problems
- Fixed Windows path compatibility
- Fixed subprocess execution reliability
- Fixed drag-and-drop UI consistency
- Fixed responsiveness on mobile

---

**Last Updated**: January 2024
**Status**: Actively Maintained
