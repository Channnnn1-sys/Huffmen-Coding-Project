# Project Defense Notes

## Likely Professor Questions

### 1. What problem does this project solve?
- It demonstrates lossless compression using Huffman coding.
- The app lets users upload files, compress them with a native C++ engine, and download the results through Flask-managed routes and ZIP packaging.
- It also supports decompression to restore the original file.
- TXT files are the primary effective evaluation target because repeated symbols make Huffman coding useful.

### 2. Why use both Python and C++?
- Flask provides the lightweight web interface, HTTP layer, and deployment integration.
- C++ is the primary computational core because it performs the real Huffman compression and decompression work efficiently in compiled form.
- This hybrid design shows how languages can work together in real applications.

### 3. How does the app stay stateless?
- All uploads and output files are stored in temporary directories created per request.
- `tempfile.TemporaryDirectory()` automatically deletes files after processing.
- The server does not keep user files on disk permanently.

### 4. How do users download files if nothing is stored?
- The backend packages results into ZIP archives and encodes them with base64.
- The frontend client decodes the base64 payload and triggers a browser download.
- This avoids server-side persistence while still delivering files.

### 5. How does the C++ compressor understand file content?
- `huffcompress.cpp` reads the input file in binary mode.
- It counts byte frequencies, builds a Huffman tree, and generates prefix codes.
- It writes a header with metadata and encodes the file contents bit-by-bit.

### 6. What are the main limitations?
- It is not designed for extremely large files or streaming compression.
- Base64 encoding adds memory overhead during transfer.
- The web UI uses synchronous request handling for simplicity.

### 7. How does the system prevent unsafe file names?
- Flask uses `secure_filename()` from Werkzeug.
- ZIP extraction sanitizes internal filenames using the same helper.
- This prevents directory traversal or file overwrite attacks.

## Code Walkthrough Notes

### `main.py`
- **Configuration**: upload size, secret key, analysis constants.
- **Utilities**: file extension helpers, entropy computation, ZIP analysis.
- **Routes**: `/compress`, `/decompress`, `/about`, `/debug`.
- **Subprocess logic**: `run_compressor()` handles external binary execution.
- **Startup validation**: `verify_compressor_binaries()` ensures C++ binaries exist.

### `compressor/huffcompress.cpp`
- Builds frequency table from file bytes.
- Constructs a Huffman tree using a priority queue.
- Encodes the file with a header containing symbol codes.
- Outputs a custom `.bin` format with metadata.

### `compressor/huffdecompress.cpp`
- Reads the custom header and Huffman code table.
- Converts compressed bytes back to a bit string.
- Reconstructs original bytes by matching Huffman codes.
- Restores file extension from the embedded metadata.

### Frontend Interaction
- The browser uploads files to `/compress` or `/decompress`.
- Responses include `data_b64` for download archives.
- The client creates a download link from the base64 payload.

## Design Decisions

### Why use temporary directories?
- It avoids permanent storage on a web server.
- It makes the app safe for cloud platforms like Render.
- Temporary directories are simple and automatically cleaned up.

### Why return ZIP archives instead of raw binary?
- Bundling output with metadata improves user experience.
- ZIP files can contain both the result and a `metadata.json` summary.
- This preserves the original filename inside a safe downloadable package.

### Why include entropy and file analysis?
- It adds educational value beyond just compressing files.
- High entropy warnings help users understand when compression may be ineffective.
- Office file analysis explains why some container files behave differently.

## Limitations of the Project

- Not optimized for large streaming uploads.
- Not production hardened with authentication or rate limiting.
- Uses synchronous request processing; concurrency depends on the WSGI server.
- The C++ compressor uses a custom format rather than a standard archive format, which keeps the project educational and easy to explain.
- Some binary files such as PDFs, DOCX, JPG, and MP4 may expand because they already contain high entropy or internal compression, which reduces the benefit of additional prefix-free Huffman coding.
- UI is basic and meant for demonstration rather than enterprise use.

## Planned Future Improvements

- Add a worker queue or asynchronous file processing.
- Support larger files with streaming compression.
- Add unit tests for Flask routes and helper functions.
- Improve UI feedback for long-running jobs.
- Add user authentication and request throttling for production.
- Offer a downloadable compressed file directly instead of ZIP when appropriate.

## Defensible Points

- The project separates concerns clearly: web handling, file management, subprocess execution, and compression logic.
- The use of temporary directories is a strong design choice for cloud safety, and it also keeps the Flask layer lightweight.
- The code avoids dangerous filename handling and returns safe JSON responses.
- The integration between Python and C++ demonstrates practical interoperability and supports the academic claim that the system uses a native C++ computational core with a Flask interface layer.
- The project delivers the same feature set while improving readability and maintainability.
