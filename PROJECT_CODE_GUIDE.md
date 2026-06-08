# Project Code Guide

## Overview
This repository implements a small educational web application for file compression and decompression using Huffman coding.

- Backend: `main.py` uses Flask as the lightweight interface and request layer.
- Computational core: native C++ binaries in `compressor/` (`huffcompress` / `huffdecompress`) perform the real Huffman encoding and decoding.
- Frontend: HTML templates in `templates/` and static CSS/JS in `static/`.
- Deployment: designed for local use and Render/Linux cloud deployment.

The app uses temporary directories for all uploads and outputs. No files are permanently stored on the server, which matches the stateless cloud deployment model. Python remains responsible for the web layer, while the native C++ engine remains responsible for the actual compression computations. This separation supports the project narrative: Flask interfaces with the browser, while C++ provides the compiled processing core.

## Architecture
The app is intentionally simple and beginner-friendly.

- `main.py` contains configuration, utility helpers, Flask routes, error handlers, and startup validation.
- Uploads are processed in an isolated `tempfile.TemporaryDirectory()` for each request.
- The Python backend delegates actual Huffman encoding/decoding to compiled C++ executables.
- Results are returned as base64-encoded ZIP bundles so the browser can download the output without persistent storage.

## Frontend to Backend Flow
1. The user visits a route such as `/compress` or `/decompress`.
2. The browser displays a form allowing one or more files to be uploaded.
3. The frontend sends a `POST` request with `multipart/form-data` to the backend route.
4. Flask receives the files in `request.files`.
5. The backend saves uploads in a temporary directory, processes them, builds ZIP packages, and returns JSON containing base64 payloads.
6. The browser uses the base64 payload to trigger downloads for the user.

## Request Lifecycle
The full lifecycle for a compress or decompress request is:

1. The browser sends a `multipart/form-data` request to `/compress` or `/decompress`.
2. Flask validates the incoming files, sanitizes names, and creates a fresh `TemporaryDirectory()` for that request.
3. The Python layer performs light analysis (entropy, warnings, optional Office deep scan) and prepares the file for the C++ engine.
4. The Python layer calls the native C++ executable through `subprocess.run()`.
5. The generated output is read back, zipped, base64-encoded, and returned to the browser.
6. The temporary directory is cleaned automatically when the request ends.

1. Validate that the `files` field exists and contains uploads.
2. Create a temporary session directory with `tempfile.TemporaryDirectory()`.
3. Save uploaded file(s) in that temporary directory.
4. Perform file analysis or safe extraction as needed.
5. Run the C++ binary using `subprocess.run()`.
6. Load the generated output file into memory.
7. Create a ZIP archive and encode it to base64.
8. Return JSON to the client.
9. Exit the `with tempfile.TemporaryDirectory()` block, which removes all temp files.

## Compression Workflow
The compression workflow is in the `/compress` route and is intentionally simple:

- Flask receives the upload.
- The file is saved in a temporary session directory.
- The app computes entropy and other lightweight analysis values.
- The C++ compressor performs the actual Huffman encoding step.
- Python packages the result and returns it to the browser.

- Each uploaded file is saved temporarily.
- The app performs optional analysis:
  - entropy estimation for randomness detection
  - Office ZIP text-layer scan for `.docx`, `.pptx`, `.xlsx`
- The file is passed to the `huffcompress` executable, which remains the real computation engine.
- After compression completes, the app reads the generated `-compressed.bin` file.
- It creates metadata and packages the compressed file into a ZIP archive.
- The ZIP archive is encoded to base64 and returned in JSON.

### Why ZIP + base64?
- The server remains stateless.
- The browser can download a single archive containing the output and metadata.
- There is no permanent server-side storage of processed files.

## Decompression Workflow
The decompression workflow is in the `/decompress` route and follows the same pattern in reverse:

- The uploaded `.bin` file or ZIP package is validated.
- The Python layer extracts the first supported compressed file when needed.
- The C++ decompressor restores the original file.
- Python returns the restored file inside a ZIP archive for download.

- Uploaded file(s) can be raw `.bin` output or ZIP archives containing `.bin` files.
- Uploaded ZIPs are inspected safely and the first supported `.bin` file is extracted.
- The extracted or uploaded binary is passed to `huffdecompress`.
- The resulting restored file is read, zipped, and encoded to base64.
- The server returns JSON containing the downloadable restore archive.

## How Flask Routes Work
Routes are defined in `main.py` using Flask decorators.

- `/`: Home page.
- `/compress`: GET renders `compress.html`; POST processes compression.
- `/decompress`: GET renders `decompress.html`; POST processes decompression.
- `/about`: Render about page.
- `/debug`: Return environment and binary status JSON.

Each POST route follows a consistent pattern:

- validate inputs
- create temporary workspace
- process each uploaded file
- collect results
- return JSON response

## How Templates Work
Templates are stored in `templates/`.

- `index.html`: landing page and navigation.
- `compress.html`: compression form.
- `decompress.html`: decompression form.
- `about.html`: project information.

Flask automatically finds templates under the `templates/` directory.
Each route calls `render_template()` to serve the HTML page.

## How Uploads Are Handled
Uploads are handled by Flask's `request.files` object.

- The app checks that the `files` field is present.
- Each file is saved with `secure_filename()` to avoid dangerous filenames.
- Files are stored in a temporary directory created for that request.
- All temporary upload files are deleted automatically when the request ends.

Security note: `secure_filename()` prevents directory traversal attacks from filenames.

## How Temporary Directories Work
The app uses `tempfile.TemporaryDirectory()` for session-scoped storage.

- Each request gets a fresh temporary directory.
- Uploaded files and generated outputs are written there.
- After request processing completes, the directory is deleted.
- This prevents stale files from accumulating on the server.

## How Subprocess Communicates with the C++ Executables
The helper `run_compressor()` handles subprocess execution.

- Validates the compressor binary exists and is executable.
- Uses `subprocess.run()` with `capture_output=True` and `text=True`.
- Sets a timeout based on file size to avoid hanging processes.
- Checks the binary's return code and stderr for errors.
- Locates the generated output file in the temp directory.

This isolates binary execution from web request handling and provides detailed error logging.

## Deployment on Render
The Render configuration is defined in `render.yaml`.

Key deployment behavior:

- Build command compiles the C++ binaries.
- Python dependencies are installed from `requirements.txt`.
- The service starts with Gunicorn using `main:app`.

Render and other cloud hosts can run the app without relying on permanent local storage because all work is done in temporary directories.

## Common File Locations
- `main.py`: backend logic and routes
- `compressor/`: C++ source and binaries
- `templates/`: HTML views
- `static/`: CSS and JavaScript assets
- `requirements.txt`: Python dependencies
- `render.yaml`: Render deployment configuration

## Security Considerations
- `SECRET_KEY` is configurable via environment variable.
- The upload field uses `secure_filename()`.
- ZIP extraction uses a safe extraction helper and sanitizes internal filenames.
- The file size limit is enforced with `MAX_CONTENT_LENGTH`.
- The app avoids permanent file storage.

## Deployment Notes
- For local development, run `main.py` directly.
- For Linux/macOS, compile C++ binaries with `build.sh`.
- For Windows, use `build.bat` or a compatible compiler.
- For Render, the `render.yaml` build command compiles the binaries before starting Gunicorn.

## Practical Advice for Students
- Keep the code simple and explain each step: upload, analysis, compression, packaging, and cleanup.
- Highlight the hybrid architecture: Python is the web layer, C++ is the compression engine.
- Emphasize statelessness: temporary directories are created and deleted per request.
- Understand how base64 and ZIP packaging let the browser download files without server-side storage.
