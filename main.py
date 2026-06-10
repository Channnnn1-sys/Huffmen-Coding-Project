"""
Huffman File Compression Web Application

This project presents a native C++ Huffman compression engine exposed through
Flask as the lightweight web interface and deployment layer.

Python handles HTTP requests, uploads, temporary session directories, ZIP
packaging, and browser download responses. The actual Huffman compression and
reconstruction remain in the compiled C++ executables for the real
computational work.
"""

import base64
import json
import logging
import os
import platform
import re
import sys
import subprocess
import tempfile
import zipfile
from collections import Counter
from datetime import datetime
from math import log2
from pathlib import Path, PurePosixPath
from uuid import uuid4

from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

#* ============================================================================
#* LOGGING CONFIGURATION
#* ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

#* ============================================================================
#* CONFIGURATION
#* ============================================================================

app = Flask(__name__)

#! Security and upload configuration
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  #* 100MB max upload

#! File type restrictions
#? The project now accepts arbitrary file types. Extension-based
#? whitelisting was removed to support binary and non-text payloads.
#? Empty-file validation is still performed at runtime.

#* Analysis constants for entropy detection
ZIP_BASED_OFFICE_EXTENSIONS = {"docx", "pptx", "xlsx"}
HIGH_ENTROPY_WARNING_EXTENSIONS = {
    "zip", "rar", "7z",
    "jpg", "jpeg", "png", "gif",
    "mp4", "mp3", "pdf"
}
SAMPLED_ENTROPY_BYTES = 100 * 1024
HIGH_ENTROPY_THRESHOLD = 7.3
COMPRESSED_SUFFIX = "-compressed.bin"

#* Directory paths for compressor binaries
BASE_DIR = Path(__file__).parent
COMPRESSOR_DIR = BASE_DIR / "compressor"

#* Temporary download storage for direct file transfers
DOWNLOAD_ROOT = Path(os.environ.get("HUFFMAN_DOWNLOAD_DIR", tempfile.gettempdir())) / "huffman_downloads"
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
DOWNLOAD_EXPIRATION_SECONDS = 15 * 60  #* downloads expire after 15 minutes

#! Detect platform and set binary names
def get_compressor_binary(name):
    """Get the path to a compressor binary based on OS.
    
    Supports:
    - Windows: huffcompress.exe, huffdecompress.exe
    - Linux/macOS: huffcompress, huffdecompress
    - Custom path via HUFFMAN_COMPRESSOR_DIR environment variable
    
    Args:
        name: 'compress' or 'decompress'
        
    Returns:
        Path to the executable (absolute path)
    """
    binary_name = f"huff{name}"
    
    #! Allow custom compressor directory via environment variable
    custom_dir = os.environ.get("HUFFMAN_COMPRESSOR_DIR")
    if custom_dir:
        compressor_dir = Path(custom_dir)
    else:
        compressor_dir = COMPRESSOR_DIR
    
    #* On Windows, add .exe extension
    if platform.system() == "Windows":
        binary_path = compressor_dir / f"{binary_name}.exe"
    else:
        binary_path = compressor_dir / binary_name
    
    return binary_path.resolve()

COMPRESS_EXE = get_compressor_binary("compress")
DECOMPRESS_EXE = get_compressor_binary("decompress")

#* Startup logging - verify binary paths are correct
logger.info(f"Platform: {platform.system()}")
logger.info(f"Base directory: {BASE_DIR}")
logger.info(f"Compressor directory: {COMPRESSOR_DIR}")
logger.info(f"Compress binary: {COMPRESS_EXE}")
logger.info(f"Decompress binary: {DECOMPRESS_EXE}")


#* ============================================================================
#* UTILITY FUNCTIONS
#* ============================================================================

def allowed_file(filename, operation="compress"):
    """Allow any filename (remove extension whitelist).

    This preserves a single responsibility: check that a filename
    was supplied. Actual content validation (empty file, corrupted
    ZIP, compressor errors) is handled during processing.
    """
    return bool(filename and filename.strip())


def get_extension(filename):
    """Return the normalized file extension without a leading dot."""
    return Path(filename).suffix.lstrip('.').lower()


def compute_entropy(byte_sequence):
    """Estimate Shannon entropy in bits per byte.

    This is a lightweight Python-side heuristic for user guidance.
    The actual Huffman coding work is still performed by the native C++ engine.
    """
    if not byte_sequence:
        return 0.0

    counts = Counter(byte_sequence)
    length = len(byte_sequence)
    entropy = 0.0
    for count in counts.values():
        probability = count / length
        entropy -= probability * log2(probability)
    return entropy


def sample_file_bytes(path, max_bytes=SAMPLED_ENTROPY_BYTES):
    """#* Sample initial bytes from file for entropy analysis."""
    try:
        with open(path, 'rb') as f:
            return f.read(max_bytes)
    except Exception:
        return b''


def count_byte_frequencies(path, sample_limit=None):
    counts = [0] * 256
    total = 0
    try:
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                for b in chunk:
                    counts[b] += 1
                total += len(chunk)
                if sample_limit and total >= sample_limit:
                    break
    except Exception:
        pass
    return counts, total


def build_huffman_lengths(counts):
    """Return a mapping of byte values to Huffman code lengths.
    
    #* Used for compression ratio analysis before actual C++ compression.
    """
    import heapq

    class HuffmanNode:
        def __init__(self, weight, byte=None, left=None, right=None):
            self.weight = weight
            self.byte = byte
            self.left = left
            self.right = right
        def __lt__(self, other):
            return self.weight < other.weight

    heap = []
    for byte_value, freq in enumerate(counts):
        if freq > 0:
            heapq.heappush(heap, HuffmanNode(freq, byte=byte_value))

    if not heap:
        return {}

    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        merged = HuffmanNode(left.weight + right.weight, left=left, right=right)
        heapq.heappush(heap, merged)

    root = heap[0]
    lengths = {}

    def walk(node, depth):
        if node is None:
            return
        if node.byte is not None:
            lengths[node.byte] = max(1, depth)
            return
        walk(node.left, depth + 1)
        walk(node.right, depth + 1)

    walk(root, 0)
    return lengths


def analyze_office_archive(path):
    """Inspect Office ZIP containers and report text/XML layer metrics.
    
    #! Deep scans Office files (docx, pptx, xlsx) to warn users about
    #! XML-heavy content which may have inherent compression.
    """
    details = {
        "office_archive": False,
        "office_xml_files": 0,
        "office_xml_total_bytes": 0,
        "office_xml_ratio": 0.0,
        "office_files": [],
        "office_message": None,
    }

    ext = get_extension(path.name)
    if ext not in ZIP_BASED_OFFICE_EXTENSIONS:
        return details

    try:
        with zipfile.ZipFile(path, 'r') as archive:
            details["office_archive"] = True
            text_entries = []
            for info in archive.infolist():
                name = info.filename
                if re.search(r'^(word/|ppt/|xl/|docProps/).*\.xml$', name, re.IGNORECASE) or name.lower() in {
                    'xl/sharedstrings.xml',
                    'word/document.xml',
                    'ppt/slides/slide1.xml'
                }:
                    text_entries.append({
                        "name": name,
                        "compressed_size": info.compress_size,
                        "uncompressed_size": info.file_size,
                    })
                    details["office_xml_total_bytes"] += info.file_size

            details["office_xml_files"] = len(text_entries)
            details["office_files"] = text_entries
            total_size = path.stat().st_size if path.exists() else 0
            details["office_xml_ratio"] = round(
                (details["office_xml_total_bytes"] / total_size * 100) if total_size > 0 else 0.0,
                2
            )
            details["office_message"] = (
                f"Deep scan detected {details['office_xml_files']} XML text layers inside this Office archive. "
                f"These text-heavy sections account for {details['office_xml_ratio']}% of the container's raw content. "
                "Actual Huffman compression is still applied to the uploaded file, but this analysis helps set realistic expectations."
            )
    except zipfile.BadZipFile:
        details["office_message"] = "Office file is not a valid ZIP container or is corrupted. Deep scan could not be completed."
    except Exception as err:
        #! Log deep scan failures but don't break the operation
        logger.warning(f"Office deep scan failed: {err}")
        details["office_message"] = "Office deep scan encountered an error during content analysis."

    return details


def create_compression_report(path, compressed_size, sample_limit=1024 * 1024):
    """Generate lightweight compression statistics for the browser.

    These values help explain expected performance to the user.
    The real encoding/decoding work remains in the compiled C++ engine.
    """
    original_size = path.stat().st_size if path.exists() else 0
    sample_bytes = sample_file_bytes(path)
    entropy = compute_entropy(sample_bytes)
    counts, total_counts = count_byte_frequencies(path, sample_limit=sample_limit if original_size > 10 * 1024 * 1024 else None)
    huffman_lengths = build_huffman_lengths(counts)
    total_symbols = sum(counts)
    avg_bits = 8.0
    if total_symbols > 0 and huffman_lengths:
        bit_sum = sum(counts[b] * huffman_lengths.get(b, 8) for b in range(256))
        avg_bits = bit_sum / total_symbols

    #* Find top 5 most frequent bytes for display
    top_symbols = []
    for byte_value, freq in sorted(((i, freq) for i, freq in enumerate(counts) if freq > 0), key=lambda x: x[1], reverse=True)[:5]:
        top_symbols.append({
            "byte": byte_value,
            "frequency": freq,
            "code_length": huffman_lengths.get(byte_value, 8)
        })

    return {
        "original_size": original_size,
        "compressed_size": compressed_size,
        "compression_ratio": round((compressed_size / original_size * 100) if original_size > 0 else 0.0, 2),
        "saved_bytes": original_size - compressed_size,
        "entropy": round(entropy, 4),
        #! Alert if file is high-entropy (already compressed)
        "entropy_warning": (
            "This file appears highly random or already compressed. Additional Huffman compression may not yield meaningful savings."
            if entropy >= HIGH_ENTROPY_THRESHOLD else None
        ),
        "average_bits_per_symbol": round(avg_bits, 4),
        "efficiency_vs_8bit": round((8.0 - avg_bits) / 8.0 * 100.0 if avg_bits < 8 else 0.0, 2),
        "top_symbols": top_symbols,
        "file_type": get_extension(path.name)
    }


def make_entropy_warning(filename, entropy):
    """#* Generate user-friendly warning message for high-entropy files."""
    ext = get_extension(filename)
    warnings = []
    if ext in HIGH_ENTROPY_WARNING_EXTENSIONS:
        warnings.append("This file type is often already compressed or contains binary data.")
    if entropy >= HIGH_ENTROPY_THRESHOLD:
        warnings.append(
            "Entropy analysis indicates a high degree of randomness. Additional Huffman compression may not significantly reduce file size."
        )
    return " ".join(warnings) if warnings else None


def safe_compressed_filename(filename):
    """#* Ensure output filename has -compressed.bin suffix for consistency."""
    if filename.endswith(COMPRESSED_SUFFIX):
        return filename
    base, ext = os.path.splitext(filename)
    return f"{base}{COMPRESSED_SUFFIX}"


def maybe_timeout_for_size(filesize):
    """#* Choose a timeout window based on file size.
    
    Larger files need more time for C++ processing.
    """
    if filesize > 50 * 1024 * 1024:
        return 120
    if filesize > 10 * 1024 * 1024:
        return 60
    return 30


def save_uploaded_file(file_storage, target_dir, filename=None):
    """#* Persist an uploaded file in the temporary session directory."""
    safe_name = secure_filename(filename or file_storage.filename)
    if not safe_name:
        raise ValueError("Uploaded file must have a filename")

    saved_path = target_dir / safe_name
    file_storage.save(str(saved_path))
    return saved_path


def build_response_archive_bytes(content_bytes, inner_filename, archive_name, metadata, target_dir):
    """#* Create a ZIP archive in temporary storage and return its base64 payload.
    
    #* This helper is retained for backwards compatibility, but the application
    #* now prefers direct file downloads to avoid memory pressure.
    """
    archive_path = target_dir / archive_name
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(inner_filename, content_bytes)
        archive.writestr('metadata.json', json.dumps(metadata, indent=2))
    return base64.b64encode(archive_path.read_bytes()).decode()


def build_response_archive_file(content_path, inner_filename, archive_name, metadata, target_dir):
    """#* Create a ZIP archive on disk from an existing file.

    Writing the archive to disk avoids loading the full ZIP payload into memory.
    """
    archive_path = target_dir / archive_name
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(content_path, arcname=inner_filename)
        archive.writestr('metadata.json', json.dumps(metadata, indent=2))
    return archive_path


def cleanup_expired_downloads():
    """Remove stale temporary download directories from disk."""
    now = time.time()
    for item in DOWNLOAD_ROOT.iterdir():
        try:
            if not item.is_dir():
                continue
            age = now - item.stat().st_mtime
            if age > DOWNLOAD_EXPIRATION_SECONDS:
                logger.info("Removing expired download directory: %s", item)
                shutil.rmtree(item)
        except Exception as exc:
            logger.warning("Failed to cleanup download item %s: %s", item, exc)


def create_download_directory():
    """Create a new clean download directory for a single request."""
    download_token = uuid4().hex
    download_dir = DOWNLOAD_ROOT / download_token
    download_dir.mkdir(parents=True, exist_ok=False)
    return download_token, download_dir


def safe_download_path(token, filename):
    """Resolve a download path safely and prevent path traversal."""
    if not re.fullmatch(r'^[A-Za-z0-9_-]+$', token):
        return None

    safe_filename = secure_filename(filename)
    if not safe_filename:
        return None

    download_path = DOWNLOAD_ROOT / token / safe_filename
    try:
        download_path = download_path.resolve()
        if not str(download_path).startswith(str(DOWNLOAD_ROOT.resolve())):
            return None
    except Exception:
        return None

    return download_path


def sha256_hash(path):
    """#* Compute the SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def read_compressed_header(compressed_path):
    """Read Huffman compressed header fields for validation."""
    try:
        with open(compressed_path, 'rb') as f:
            magic = f.read(4)
            if magic != b'HUFF':
                return None, 'Invalid compressed file magic header.'

            version = f.read(1)
            if not version or version[0] != 1:
                return None, 'Unsupported compressed file version.'

            raw_symbols = f.read(4)
            raw_chars = f.read(4)
            if len(raw_symbols) != 4 or len(raw_chars) != 4:
                return None, 'Incomplete compressed file header.'

            unique_symbols = int.from_bytes(raw_symbols, 'little', signed=True)
            expected_chars = int.from_bytes(raw_chars, 'little', signed=True)

            ext_len_bytes = f.read(1)
            if len(ext_len_bytes) != 1:
                return None, 'Missing extension byte in compressed header.'

            ext_len = ext_len_bytes[0]
            extension = f.read(ext_len).decode('utf-8', errors='replace') if ext_len else ''

            if unique_symbols < 0 or unique_symbols > 256 or expected_chars < 0:
                return None, 'Invalid compressed header values.'

            return {
                'unique_symbols': unique_symbols,
                'expected_chars': expected_chars,
                'extension': extension,
            }, None
    except Exception as exc:
        return None, f'Failed to read compressed header: {exc}'


def build_download_metadata(operation, original_name, output_name, size_info, extra=None):
    """Return the metadata dictionary used for downloadable ZIP results."""
    if operation == 'compress':
        metadata = {
            'algorithm': 'huffman',
            'operation': 'compress',
            'original_filename': original_name,
            'compressed_filename': output_name,
            'original_size': size_info.get('original_size', 0),
            'compressed_size': size_info.get('compressed_size', 0),
            'original_sha256': size_info.get('original_sha256'),
            'compressed_sha256': size_info.get('compressed_sha256'),
            'timestamp': datetime.now().isoformat(),
        }
    else:
        metadata = {
            'algorithm': 'huffman',
            'operation': 'decompress',
            'original_compressed': original_name,
            'decompressed_filename': output_name,
            'compressed_size': size_info.get('compressed_size', 0),
            'decompressed_size': size_info.get('decompressed_size', 0),
            'original_sha256': size_info.get('original_sha256'),
            'compressed_sha256': size_info.get('compressed_sha256'),
            'timestamp': datetime.now().isoformat(),
        }
    if extra:
        metadata.update(extra)
    return metadata


def is_safe_zip_member(info):
    """Return False for ZIP entries that may lead to path traversal or unsafe extraction."""
    filename = info.filename
    if not filename or filename.strip() == "":
        return False

    # Reject absolute paths and parent directory traversal
    if filename.startswith('/') or filename.startswith('\\'):
        return False

    normalized = PurePosixPath(filename)
    if any(part == '..' for part in normalized.parts):
        return False

    return True


def extract_compressed_bin_from_zip(zip_path, target_dir):
    """#* Safely extract a single compressed binary and optional metadata from an uploaded ZIP.

    Returns a tuple of (Path or None, metadata dict or None, error_message or None).
    """
    logger.info("Extracting compressed .bin from ZIP: %s", zip_path)
    extracted_metadata = None
    try:
        with zipfile.ZipFile(zip_path, 'r') as archive:
            members = archive.infolist()
            logger.info("ZIP contents: %s", [info.filename for info in members])

            candidates = []
            for info in members:
                if info.is_dir():
                    continue
                if not is_safe_zip_member(info):
                    error_msg = f"ZIP contains unsafe path entry: {info.filename}"
                    logger.error(error_msg)
                    return None, None, error_msg

                normalized_name = Path(info.filename).name
                if normalized_name == 'metadata.json':
                    try:
                        with archive.open(info, 'r') as source:
                            extracted_metadata = json.loads(source.read().decode('utf-8'))
                            logger.info("Loaded metadata.json from ZIP: %s", extracted_metadata)
                    except Exception as err:
                        logger.warning("Failed to read metadata.json from ZIP: %s", err)
                        extracted_metadata = None
                    continue

                if normalized_name.endswith('-compressed.bin') or normalized_name.lower().endswith('.bin'):
                    safe_name = secure_filename(normalized_name)
                    if not safe_name:
                        logger.warning("Skipping unsafe candidate name in ZIP: %s", info.filename)
                        continue
                    candidates.append((info, safe_name))

            if not candidates:
                error_msg = "No supported compressed .bin file found inside uploaded ZIP."
                logger.error(error_msg)
                return None, None, error_msg

            if len(candidates) > 1:
                names = [safe_name for _, safe_name in candidates]
                error_msg = (
                    "Uploaded ZIP contains multiple candidate .bin files: "
                    + ", ".join(names)
                    + ". Please upload a ZIP package generated by this tool with a single compressed file."
                )
                logger.error(error_msg)
                return None, None, error_msg

            info, safe_name = candidates[0]
            extracted_path = target_dir / safe_name
            with archive.open(info, 'r') as source, open(extracted_path, 'wb') as target:
                data = source.read()
                target.write(data)

            if not extracted_path.exists() or extracted_path.stat().st_size == 0:
                error_msg = "Extracted compressed file is empty or could not be created."
                logger.error(error_msg)
                return None, None, error_msg

            logger.info("Extracted compressed binary to: %s", extracted_path)
            return extracted_path, extracted_metadata, None
    except zipfile.BadZipFile:
        error_msg = "Invalid ZIP archive."
        logger.error("Invalid ZIP archive: %s", zip_path)
        return None, None, error_msg
    except Exception as exc:
        error_msg = f"Failed to extract ZIP contents: {exc}"
        logger.exception(error_msg)
        return None, None, error_msg


def find_subprocess_output(output_dir, expected_prefix):
    """Locate a single decompression output file written by the C++ binary."""
    candidates = [path for path in output_dir.iterdir() if path.is_file() and path.name.startswith(expected_prefix)]
    logger.info("Searching for subprocess output with prefix '%s' in %s", expected_prefix, output_dir)
    logger.info("Subprocess output candidates: %s", [p.name for p in candidates])
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, f"Multiple decompressed outputs found: {', '.join(p.name for p in candidates)}"
    return None, None


def run_compressor(input_file, exe_path, output_dir, timeout=30):
    """
    Execute the Huffman compressor or decompressor and resolve the generated output.

    This function keeps the backend isolated from binary details. It:
    1. Validates the executable exists
    2. Ensures Unix binaries are runnable
    3. Runs the compressor or decompressor
    4. Finds the generated output file in the temporary session directory

    Args:
        input_file: Path object for the saved upload
        exe_path: Path object for the compressor executable
        output_dir: Temporary directory path where output files are written
        timeout: Maximum seconds to wait for the subprocess

    Returns:
        A tuple of (success, output_path, error_message).
    """
    operation = 'compress' if exe_path.name.lower().startswith('huffcompress') else 'decompress'

    logger.info("Starting %s operation", operation)
    logger.info("  Input file: %s", input_file)
    logger.info("  Executable: %s", exe_path)
    logger.info("  Output directory: %s", output_dir)
    logger.info("  Subprocess command: %s", [str(exe_path), str(input_file)])

    if not exe_path.exists() or not exe_path.is_file():
        error_msg = f"Compressor binary not found at: {exe_path}"
        logger.error(error_msg)
        return False, None, error_msg

    if not input_file.exists():
        error_msg = f"Input file not found: {input_file}"
        logger.error(error_msg)
        return False, None, error_msg

    if platform.system() != 'Windows':
        try:
            os.chmod(exe_path, 0o755)
        except Exception as exc:
            logger.warning("Could not set executable permission: %s", exc)

    try:
        result = subprocess.run(
            [str(exe_path), str(input_file)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(output_dir)
        )

        logger.info("Process return code: %s", result.returncode)
        logger.info("Process command: %s", result.args)
        if result.stdout:
            logger.info("Process stdout: %s", result.stdout.strip()[:500])
        if result.stderr:
            logger.warning("Process stderr: %s", result.stderr.strip()[:500])

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or 'Unknown error'
            logger.error("Binary failed: %s", error_msg)
            return False, None, error_msg

        if operation == 'compress':
            expected_output = output_dir / f"{input_file.stem}-compressed.bin"
            if not expected_output.exists():
                candidate, candidate_error = find_subprocess_output(output_dir, f"{input_file.stem}-compressed")
                if candidate_error:
                    error_msg = candidate_error
                    logger.error(error_msg)
                    return False, None, error_msg
                expected_output = candidate
        else:
            if input_file.name.endswith('-compressed.bin'):
                base_name = input_file.name[:-len('-compressed.bin')]
            elif input_file.suffix.lower() == '.bin':
                base_name = input_file.stem
            else:
                base_name = input_file.stem

            expected_prefix = f"{base_name}-decompressed"
            expected_output, output_error = find_subprocess_output(output_dir, expected_prefix)
            if output_error:
                logger.error(output_error)
                return False, None, output_error
            if expected_output is None:
                error_msg = f"Decompressed output file not found for input: {input_file.name}"
                logger.error(error_msg)
                return False, None, error_msg

        logger.info("Expected output file resolved to: %s", expected_output)
        if not expected_output.exists():
            error_msg = f"Expected output file was not created: {expected_output}"
            logger.error(error_msg)
            return False, None, error_msg
        if expected_output.stat().st_size == 0:
            error_msg = f"Expected output file is empty: {expected_output}"
            logger.error(error_msg)
            return False, None, error_msg

        return True, expected_output, None

    except subprocess.TimeoutExpired:
        error_msg = f"Compression timeout after {timeout} seconds"
        logger.error(error_msg)
        return False, None, error_msg
    except FileNotFoundError as exc:
        error_msg = f"Executable not found: {exc}"
        logger.error(error_msg)
        return False, None, error_msg
    except Exception as exc:
        error_msg = f"Unexpected error during {operation}: {exc}"
        logger.error(error_msg, exc_info=True)
        return False, None, error_msg


# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route("/")
def home():
    """Render home page."""
    return render_template("index.html")


@app.route("/compress", methods=["GET", "POST"])
def compress():
    """
    Handle file compression requests.

    GET: render the compression page.
    POST: save uploads in a temporary session, compress each file with the C++ engine,
    and return a JSON payload containing base64 ZIP archives for download.
    """
    if request.method == "GET":
        return render_template("compress.html")

    cleanup_expired_downloads()
    logger.info("POST /compress received request")
    if "files" not in request.files:
        logger.warning("POST /compress missing files field")
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    logger.info("POST /compress received %d file(s)", len(files))
    if not files:
        return jsonify({"error": "No files selected"}), 400

    job_id = generate_job_id()
    results = []

    with tempfile.TemporaryDirectory() as temp_session_dir:
        temp_session_path = Path(temp_session_dir)

        for uploaded_file in files:
            if not uploaded_file.filename:
                continue

            filename = secure_filename(uploaded_file.filename)
            if not allowed_file(filename, "compress"):
                results.append({
                    "filename": uploaded_file.filename,
                    "success": False,
                    "error": "Unsupported file type. Please upload a valid file."
                })
                continue

            try:
                start_time = datetime.now()
                temp_input_path = save_uploaded_file(uploaded_file, temp_session_path, filename)

                original_size = temp_input_path.stat().st_size
                original_sha256 = sha256_hash(temp_input_path)
                entropy_value = compute_entropy(sample_file_bytes(temp_input_path))
                entropy_warning = make_entropy_warning(filename, entropy_value)
                office_scan = analyze_office_archive(temp_input_path)

                timeout = maybe_timeout_for_size(original_size)
                success, output_file, error = run_compressor(
                    temp_input_path,
                    COMPRESS_EXE,
                    temp_session_path,
                    timeout=timeout
                )

                if not success:
                    results.append({
                        "filename": filename,
                        "success": False,
                        "error": error
                    })
                    continue

                compressed_sha256 = sha256_hash(output_file)
                report = create_compression_report(temp_input_path, output_file.stat().st_size)
                processing_time = (datetime.now() - start_time).total_seconds()

                compression_warning = None
                if output_file.stat().st_size > original_size:
                    compression_warning = (
                        "Compressed output is larger than the original file. "
                        "This usually happens when the input data has high entropy or is already compressed."
                    )
                    logger.warning(
                        "Ineffective compression for %s: original=%s compressed=%s",
                        filename, original_size, output_file.stat().st_size
                    )

                zip_name = f"{temp_input_path.stem}-compressed.zip"
                download_token, download_dir = create_download_directory()
                archive_path = build_response_archive_file(
                    output_file,
                    output_file.name,
                    zip_name,
                    build_download_metadata(
                        "compress",
                        filename,
                        output_file.name,
                        {
                            "original_size": report["original_size"],
                            "compressed_size": report["compressed_size"],
                            "original_sha256": original_sha256,
                            "compressed_sha256": compressed_sha256,
                        },
                        extra={
                            "compression_warning": compression_warning
                        }
                    ),
                    download_dir
                )
                download_url = url_for('download_file', token=download_token, filename=zip_name)

                results.append({
                    "filename": filename,
                    "success": True,
                    "compressed_filename": zip_name,
                    "download_url": download_url,
                    "download_size": archive_path.stat().st_size,
                    "original_size": report["original_size"],
                    "compressed_size": report["compressed_size"],
                    "original_sha256": original_sha256,
                    "compressed_sha256": compressed_sha256,
                    "compression_ratio": report["compression_ratio"],
                    "saved_bytes": report["saved_bytes"],
                    "entropy": report["entropy"],
                    "entropy_warning": report["entropy_warning"] or entropy_warning,
                    "compression_warning": compression_warning,
                    "average_bits_per_symbol": report["average_bits_per_symbol"],
                    "efficiency_vs_8bit": report["efficiency_vs_8bit"],
                    "top_symbols": report["top_symbols"],
                    "file_type": report["file_type"],
                    "deep_scan": office_scan,
                    "processing_time_seconds": round(processing_time, 3)
                })

            except Exception as exc:
                logger.exception("Unexpected error during compression")
                results.append({
                    "filename": filename,
                    "success": False,
                    "error": str(exc)
                })

    return jsonify({
        "job_id": job_id,
        "results": results,
        "timestamp": datetime.now().isoformat()
    })


def generate_job_id():
    """Generate a unique job ID."""
    return str(uuid4())[:8]


@app.route("/decompress", methods=["GET", "POST"])
def decompress():
    """
    Handle file decompression requests.

    GET: render the decompression page.
    POST: save uploads, extract valid compressed binaries, run the C++ decompressor,
    and return base64 ZIP archives with restored files.
    """
    if request.method == "GET":
        return render_template("decompress.html")

    cleanup_expired_downloads()
    logger.info("POST /decompress received request")
    if "files" not in request.files:
        logger.warning("POST /decompress missing files field")
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    logger.info("POST /decompress received %d file(s)", len(files))
    if not files:
        return jsonify({"error": "No files selected"}), 400

    job_id = generate_job_id()
    results = []

    with tempfile.TemporaryDirectory() as temp_session_dir:
        temp_session_path = Path(temp_session_dir)
        logger.info("Temporary session directory: %s", temp_session_path)

        for uploaded_file in files:
            logger.info("Received uploaded file for decompression: %s", uploaded_file.filename)
            if not uploaded_file.filename:
                continue

            filename = secure_filename(uploaded_file.filename)
            if not allowed_file(filename, "decompress"):
                results.append({
                    "filename": uploaded_file.filename,
                    "success": False,
                    "error": "Unsupported file type. Please upload a valid .bin file generated by this tool."
                })
                continue

            try:
                start_time = datetime.now()
                temp_upload_path = save_uploaded_file(uploaded_file, temp_session_path, filename)

                upload_metadata = None
                if get_extension(filename) == 'zip':
                    temp_input_path, upload_metadata, extract_error = extract_compressed_bin_from_zip(temp_upload_path, temp_session_path)
                    if extract_error:
                        results.append({
                            "filename": filename,
                            "success": False,
                            "error": extract_error
                        })
                        continue
                else:
                    safe_filename = safe_compressed_filename(filename)
                    temp_input_path = temp_session_path / safe_filename
                    if temp_upload_path.name != temp_input_path.name:
                        temp_upload_path.rename(temp_input_path)

                logger.info("Resolved decompression input path: %s", temp_input_path)
                if not temp_input_path.exists() or not temp_input_path.is_file():
                    error_msg = f"Processed input binary not found: {temp_input_path.name}"
                    logger.error(error_msg)
                    results.append({
                        "filename": filename,
                        "success": False,
                        "error": error_msg
                    })
                    continue
                if temp_input_path.stat().st_size == 0:
                    error_msg = f"Processed input binary is empty: {temp_input_path.name}"
                    logger.error(error_msg)
                    results.append({
                        "filename": filename,
                        "success": False,
                        "error": error_msg
                    })
                    continue

                timeout = maybe_timeout_for_size(temp_input_path.stat().st_size)
                success, output_file, error = run_compressor(
                    temp_input_path,
                    DECOMPRESS_EXE,
                    temp_session_path,
                    timeout=timeout
                )

                if not success:
                    results.append({
                        "filename": filename,
                        "success": False,
                        "error": error
                    })
                    continue

                logger.info("Decompress completed. Output file: %s", output_file)
                logger.info("Temporary session contents after decompression: %s", [p.name for p in temp_session_path.iterdir()])

                compressed_size = temp_input_path.stat().st_size
                decompressed_size = output_file.stat().st_size
                decompressed_sha256 = sha256_hash(output_file)

                header_info, header_error = read_compressed_header(temp_input_path)
                header_verified = None
                if header_info is not None:
                    header_verified = decompressed_size == header_info['expected_chars']
                    logger.info(
                        "Compressed file header expected chars=%s, decompressed size=%s, header_verified=%s",
                        header_info['expected_chars'], decompressed_size, header_verified
                    )
                elif header_error:
                    logger.warning("Compressed header validation failed: %s", header_error)

                integrity_verified = None
                if upload_metadata and upload_metadata.get('original_sha256'):
                    integrity_verified = upload_metadata['original_sha256'] == decompressed_sha256
                    logger.info(
                        "Integrity hash comparison: expected=%s restored=%s verified=%s",
                        upload_metadata['original_sha256'], decompressed_sha256, integrity_verified
                    )
                elif header_verified is False:
                    integrity_verified = False

                zip_name = f"{output_file.stem}.zip"
                download_token, download_dir = create_download_directory()
                archive_path = build_response_archive_file(
                    output_file,
                    output_file.name,
                    zip_name,
                    build_download_metadata(
                        "decompress",
                        filename,
                        output_file.name,
                        {
                            "compressed_size": compressed_size,
                            "decompressed_size": decompressed_size,
                            "original_sha256": upload_metadata.get('original_sha256') if upload_metadata else None,
                            "compressed_sha256": upload_metadata.get('compressed_sha256') if upload_metadata else None,
                            "decompressed_sha256": decompressed_sha256,
                        },
                        extra={
                            'integrity_verified': integrity_verified,
                            'header_verified': header_verified,
                            'header_expected_chars': header_info['expected_chars'] if header_info else None,
                            'header_extension': header_info['extension'] if header_info else None,
                        }
                    ),
                    download_dir
                )
                download_url = url_for('download_file', token=download_token, filename=zip_name)

                results.append({
                    "filename": filename,
                    "success": True,
                    "decompressed_filename": zip_name,
                    "download_url": download_url,
                    "download_size": archive_path.stat().st_size,
                    "compressed_size": compressed_size,
                    "decompressed_size": decompressed_size,
                    "decompressed_sha256": decompressed_sha256,
                    "integrity_verified": integrity_verified,
                    "header_verified": header_verified,
                    "processing_time_seconds": round(processing_time, 3)
                })

            except Exception as exc:
                logger.exception("Unexpected error during decompression")
                results.append({
                    "filename": filename,
                    "success": False,
                    "error": str(exc)
                })

    return jsonify({
        "job_id": job_id,
        "results": results,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/download/<token>/<path:filename>")
def download_file(token, filename):
    """Serve temporary ZIP download files directly.

    This endpoint keeps the download transfer separate from the JSON API.
    It validates the token and filename, serves the file with an attachment header,
    and avoids loading the entire payload into server memory.
    """
    cleanup_expired_downloads()
    download_path = safe_download_path(token, filename)
    if not download_path or not download_path.exists() or not download_path.is_file():
        logger.warning("Download request failed for token=%s filename=%s", token, filename)
        abort(404)

    logger.info("Serving download file: %s", download_path)
    return send_file(
        str(download_path),
        as_attachment=True,
        download_name=download_path.name,
        mimetype='application/zip'
    )


@app.route("/about")
def about():
    """Render about page."""
    return render_template("about.html")


@app.route("/debug")
def debug():
    """Debug endpoint to show environment and deployment information."""
    import shutil
    
    debug_info = {
        "environment": {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "python_version": platform.python_version(),
            "cwd": os.getcwd(),
        },
        "paths": {
            "base_dir": str(BASE_DIR),
            "compressor_dir": str(COMPRESSOR_DIR),
            "compress_exe": str(COMPRESS_EXE),
            "decompress_exe": str(DECOMPRESS_EXE),
        },
        "binaries": {
            "compress": {
                "path": str(COMPRESS_EXE),
                "exists": COMPRESS_EXE.exists(),
                "is_file": COMPRESS_EXE.is_file() if COMPRESS_EXE.exists() else False,
                "size": COMPRESS_EXE.stat().st_size if COMPRESS_EXE.exists() else None,
            },
            "decompress": {
                "path": str(DECOMPRESS_EXE),
                "exists": DECOMPRESS_EXE.exists(),
                "is_file": DECOMPRESS_EXE.is_file() if DECOMPRESS_EXE.exists() else False,
                "size": DECOMPRESS_EXE.stat().st_size if DECOMPRESS_EXE.exists() else None,
            }
        },
        "compressor_dir_contents": [
            {
                "name": f.name,
                "type": "directory" if f.is_dir() else "file",
                "size": f.stat().st_size if f.is_file() else None,
            }
            for f in COMPRESSOR_DIR.iterdir()
        ],
        "which_gcc": shutil.which("g++") or "NOT FOUND",
        "which_compress": shutil.which(str(COMPRESS_EXE)) or "NOT FOUND",
    }
    
    return jsonify(debug_info)


@app.errorhandler(413)
def too_large(e):
    """Handle files that exceed max size."""
    return jsonify({"error": "File too large. Maximum size is 100MB"}), 413


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors."""
    return jsonify({"error": "Page not found"}), 404


@app.errorhandler(500)
def server_error(e):
    """Handle server errors."""
    return jsonify({"error": "Internal server error"}), 500


# ============================================================================
# APPLICATION STARTUP
# ============================================================================

def verify_compressor_binaries():
    """
    Verify that compressor executables exist and are executable.
    Provides helpful build instructions if missing.
    """
    print("\n" + "=" * 80)
    print("🔍 COMPRESSOR BINARY VERIFICATION")
    print("=" * 80)

    print(f"📍 Platform: {platform.system()}")
    print(f"📍 Current Working Directory: {os.getcwd()}")
    print(f"📍 Base Directory: {BASE_DIR}")
    print(f"📍 Compressor Directory: {COMPRESSOR_DIR}")
    print(f"📍 Expected Compress Binary: {COMPRESS_EXE}")
    print(f"📍 Expected Decompress Binary: {DECOMPRESS_EXE}")
    print()

    missing_binaries = []
    invalid_binaries = []

    for binary_name, binary_path in [("COMPRESS", COMPRESS_EXE), ("DECOMPRESS", DECOMPRESS_EXE)]:
        print(f"🔍 Checking {binary_name}:")
        print(f"   Path: {binary_path}")
        print(f"   Exists: {binary_path.exists()}")

        if binary_path.exists():
            print(f"   Is file: {binary_path.is_file()}")
            if binary_path.is_file():
                size = binary_path.stat().st_size
                print(f"   Size: {size} bytes")

                # Check if executable
                if platform.system() != "Windows":
                    mode = binary_path.stat().st_mode
                    is_executable = bool(mode & 0o111)
                    print(f"   Permissions: {oct(mode)}")
                    print(f"   Executable: {is_executable}")
                    if not is_executable:
                        invalid_binaries.append(binary_name)
                        print(f"   ❌ NOT EXECUTABLE")
                    else:
                        print(f"   ✅ EXECUTABLE")
                else:
                    print(f"   Windows binary (permissions not checked)")
            else:
                invalid_binaries.append(f"{binary_name} (not a file)")
                print(f"   ❌ NOT A FILE")
        else:
            missing_binaries.append(binary_name)
            print(f"   ❌ NOT FOUND")
        print()

    # Show directory contents
    print("📁 Compressor Directory Contents:")
    try:
        contents = list(COMPRESSOR_DIR.iterdir())
        if contents:
            for item in contents:
                item_type = "DIR" if item.is_dir() else "FILE"
                size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
                print(f"   {item.name} [{item_type}]{size}")
        else:
            print("   (empty)")
    except Exception as e:
        print(f"   Error reading directory: {e}")
    print()

    print("=" * 80)

    if missing_binaries or invalid_binaries:
        error_msg = f"❌ COMPRESSOR BINARIES NOT READY!\n\n"

        if missing_binaries:
            error_msg += f"Missing binaries: {', '.join(missing_binaries)}\n"

        if invalid_binaries:
            error_msg += f"Invalid binaries: {', '.join(invalid_binaries)}\n"

        # Provide platform-specific help
        if platform.system() == "Windows":
            error_msg += f"\n--- Windows Instructions ---\n"
            error_msg += f"To build the C++ compressors:\n\n"
            error_msg += f"  cd {COMPRESSOR_DIR}\n"
            error_msg += f"  g++ -O2 -o huffcompress.exe huffcompress.cpp\n"
            error_msg += f"  g++ -O2 -o huffdecompress.exe huffdecompress.cpp\n"
        else:
            error_msg += f"\n--- Linux/macOS Instructions ---\n"
            error_msg += f"To build the C++ compressors:\n\n"
            error_msg += f"  cd {COMPRESSOR_DIR}\n"
            error_msg += f"  g++ -O2 -o huffcompress huffcompress.cpp\n"
            error_msg += f"  g++ -O2 -o huffdecompress huffdecompress.cpp\n"

            # Add Render-specific guidance
            error_msg += f"\n--- Render Deployment Instructions ---\n"
            error_msg += f"If deploying to Render:\n\n"
            error_msg += f"1. Check render.yaml has correct buildCommand\n"
            error_msg += f"2. Clear build cache: In Render dashboard, click 'Clear Build Cache & Redeploy'\n"
            error_msg += f"3. Check build logs to see if g++ compilation succeeded\n"
            error_msg += f"4. Ensure render.yaml buildCommand includes:\n"
            error_msg += f"     chmod +x compile_linux.sh\n"
            error_msg += f"     ./compile_linux.sh\n"

        print(error_msg)
        logger.error(error_msg)
        sys.exit(1)
    else:
        print("✅ ALL COMPRESSOR BINARIES ARE READY!")
        logger.info("All compressor binaries verified successfully")
        print("=" * 80)


if __name__ == "__main__":
    # Verify binaries
    verify_compressor_binaries()

    print("\n" + "=" * 70)
    print("Huffman File Compression Web Application")
    print("Cloud-Native Stateless Edition (Render/Linux compatible)")
    print("=" * 70)
    print(f"Platform: {platform.system()}")
    print(f"Python Version: {platform.python_version()}")
    print(f"Base Directory: {BASE_DIR}")
    print(f"Compressor Directory: {COMPRESSOR_DIR}")
    print(f"Compress Binary: {COMPRESS_EXE}")
    print(f"Decompress Binary: {DECOMPRESS_EXE}")
    print(f"Max Upload Size: {app.config['MAX_CONTENT_LENGTH'] / (1024*1024):.0f}MB")
    print("=" * 70)
    print("Starting Flask application...\n")
    
    # Production note
    if platform.system() != "Windows":
        print("NOTE: Running on Linux/Unix. Use gunicorn for production:")
        print("  gunicorn -w 4 -b 0.0.0.0:8000 main:app")
        print()
    
    print("🔗 Web Application URLs:")
    print("   🏠 Home: http://localhost:5000")
    print("   🗜️  Compress: http://localhost:5000/compress")
    print("   📦 Decompress: http://localhost:5000/decompress")
    print("   🔍 Debug Info: http://localhost:5000/debug")
    print("=" * 80)

    app.run(debug=True, host="0.0.0.0", port=5000)
