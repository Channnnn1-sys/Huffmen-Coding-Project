"""
Huffman File Compression Web Application

This Flask app teaches file compression with a C++ Huffman engine.
It keeps the server stateless by processing uploads in temporary directories,
returning results as base64 payloads, and cleaning up immediately.
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
from pathlib import Path
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
    
    #* Uses Shannon's entropy formula to detect high-entropy (already compressed) files
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
    """#* Generate detailed compression analysis and statistics for display."""
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
    
    #* Combines compressed/decompressed file with metadata.json for easy download.
    """
    archive_path = target_dir / archive_name
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(inner_filename, content_bytes)
        archive.writestr('metadata.json', json.dumps(metadata, indent=2))
    return base64.b64encode(archive_path.read_bytes()).decode()


def build_download_metadata(operation, original_name, output_name, size_info):
    """Return the metadata dictionary used for downloadable ZIP results."""
    if operation == "compress":
        return {
            "algorithm": "huffman",
            "operation": "compress",
            "original_filename": original_name,
            "compressed_filename": output_name,
            "original_size": size_info.get("original_size", 0),
            "compressed_size": size_info.get("compressed_size", 0),
            "timestamp": datetime.now().isoformat(),
        }

    return {
        "algorithm": "huffman",
        "operation": "decompress",
        "original_compressed": original_name,
        "decompressed_filename": output_name,
        "compressed_size": size_info.get("compressed_size", 0),
        "decompressed_size": size_info.get("decompressed_size", 0),
        "timestamp": datetime.now().isoformat(),
    }


def extract_compressed_bin_from_zip(zip_path, target_dir):
    """#* Extract the first supported compressed binary from a ZIP upload safely.
    
    #! Validates ZIP structure and only extracts .bin files.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as archive:
            for info in archive.infolist():
                candidate_name = Path(info.filename).name
                if candidate_name.endswith('-compressed.bin') or candidate_name.lower().endswith('.bin'):
                    safe_name = secure_filename(candidate_name)
                    if not safe_name:
                        continue

                    extracted_path = target_dir / safe_name
                    with archive.open(info, 'r') as source, open(extracted_path, 'wb') as target:
                        target.write(source.read())
                    return extracted_path
    except zipfile.BadZipFile:
        return None
    return None


def run_compressor(input_file, exe_path, output_dir, timeout=30):
    """#! Execute the Huffman compressor or decompressor and resolve generated output.

    #* This function keeps the backend isolated from binary details. It:
    #* 1. Validates the executable exists
    #* 2. Ensures Unix binaries are runnable
    #* 3. Runs the compressor or decompressor
    #* 4. Finds the generated output file in the temporary session directory

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

    #! Validate required files and directories
    if not exe_path.exists() or not exe_path.is_file():
        error_msg = f"Compressor binary not found at: {exe_path}"
        logger.error(error_msg)
        return False, None, error_msg

    if not input_file.exists():
        error_msg = f"Input file not found: {input_file}"
        logger.error(error_msg)
        return False, None, error_msg

    #* Make binaries executable on Unix systems
    if platform.system() != 'Windows':
        try:
            os.chmod(exe_path, 0o755)
        except Exception as exc:
            logger.warning("Could not set executable permission: %s", exc)

    try:
        #* Execute the compressor binary with appropriate timeout
        result = subprocess.run(
            [str(exe_path), str(input_file)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(output_dir)
        )

        logger.info("Process return code: %s", result.returncode)
        if result.stdout:
            logger.info("Process stdout: %s", result.stdout[:200])
        if result.stderr:
            logger.warning("Process stderr: %s", result.stderr[:200])

        #! Handle execution errors
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or 'Unknown error'
            logger.error("Binary failed: %s", error_msg)
            return False, None, error_msg

        #* Locate the generated output file
        if operation == 'compress':
            expected_output = input_file.parent / f"{input_file.stem}-compressed.bin"
        else:
            base_name = input_file.stem.replace('-compressed', '')
            expected_output = None
            for candidate in output_dir.iterdir():
                if candidate.is_file() and candidate.name.startswith(f"{base_name}-decompressed"):
                    expected_output = candidate
                    break
            if expected_output is None:
                error_msg = f"Decompressed output file not found for input: {input_file.name}"
                logger.error(error_msg)
                return False, None, error_msg

        if expected_output.exists():
            return True, expected_output, None

        error_msg = f"Expected output file was not created: {expected_output}"
        logger.error(error_msg)
        return False, None, error_msg

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


#* ============================================================================
#* FLASK ROUTES
#* ============================================================================

@app.route("/")
def home():
    """#* Render home page."""
    return render_template("index.html")


@app.route("/compress", methods=["GET", "POST"])
def compress():
    """#! Handle file compression requests.

    #* GET: render the compression page.
    #* POST: save uploads in a temporary session, compress each file with the C++ engine,
    #* and return a JSON payload containing base64 ZIP archives for download.
    """
    if request.method == "GET":
        return render_template("compress.html")

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

                compressed_data = output_file.read_bytes()
                report = create_compression_report(temp_input_path, len(compressed_data))
                processing_time = (datetime.now() - start_time).total_seconds()

                zip_name = f"{temp_input_path.stem}-compressed.zip"
                metadata = build_download_metadata(
                    "compress",
                    filename,
                    output_file.name,
                    {
                        "original_size": report["original_size"],
                        "compressed_size": report["compressed_size"],
                    },
                )
                data_b64 = build_response_archive_bytes(
                    compressed_data,
                    output_file.name,
                    zip_name,
                    metadata,
                    temp_session_path
                )

                results.append({
                    "filename": filename,
                    "success": True,
                    "compressed_filename": zip_name,
                    "original_size": report["original_size"],
                    "compressed_size": report["compressed_size"],
                    "compression_ratio": report["compression_ratio"],
                    "saved_bytes": report["saved_bytes"],
                    "entropy": report["entropy"],
                    "entropy_warning": report["entropy_warning"] or entropy_warning,
                    "average_bits_per_symbol": report["average_bits_per_symbol"],
                    "efficiency_vs_8bit": report["efficiency_vs_8bit"],
                    "top_symbols": report["top_symbols"],
                    "file_type": report["file_type"],
                    "deep_scan": office_scan,
                    "processing_time_seconds": round(processing_time, 3),
                    "data_b64": data_b64
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
    """#! Handle file decompression requests.

    #* GET: render the decompression page.
    #* POST: save uploads, extract valid compressed binaries, run the C++ decompressor,
    #* and return base64 ZIP archives with restored files.
    """
    if request.method == "GET":
        return render_template("decompress.html")

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

        for uploaded_file in files:
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

                if get_extension(filename) == 'zip':
                    temp_input_path = extract_compressed_bin_from_zip(temp_upload_path, temp_session_path)
                    if not temp_input_path:
                        results.append({
                            "filename": filename,
                            "success": False,
                            "error": "No compressed .bin file found inside uploaded ZIP or ZIP is invalid."
                        })
                        continue
                else:
                    safe_filename = safe_compressed_filename(filename)
                    temp_input_path = temp_session_path / safe_filename
                    if temp_upload_path.name != temp_input_path.name:
                        temp_upload_path.rename(temp_input_path)

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

                decompressed_data = output_file.read_bytes()
                compressed_size = temp_input_path.stat().st_size
                decompressed_size = len(decompressed_data)
                processing_time = (datetime.now() - start_time).total_seconds()

                zip_name = f"{output_file.stem}-decompressed.zip"
                metadata = build_download_metadata(
                    "decompress",
                    filename,
                    output_file.name,
                    {
                        "compressed_size": compressed_size,
                        "decompressed_size": decompressed_size,
                    },
                )
                data_b64 = build_response_archive_bytes(
                    decompressed_data,
                    output_file.name,
                    zip_name,
                    metadata,
                    temp_session_path
                )

                results.append({
                    "filename": filename,
                    "success": True,
                    "decompressed_filename": zip_name,
                    "compressed_size": compressed_size,
                    "decompressed_size": decompressed_size,
                    "processing_time_seconds": round(processing_time, 3),
                    "data_b64": data_b64
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


@app.route("/about")
def about():
    """#* Render about page."""
    return render_template("about.html")


@app.route("/debug")
def debug():
    """#? Debug endpoint to show environment and deployment information."""
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
    """#! Handle files that exceed max size."""
    return jsonify({"error": "File too large. Maximum size is 100MB"}), 413


@app.errorhandler(404)
def not_found(e):
    """#! Handle 404 errors."""
    return jsonify({"error": "Page not found"}), 404


@app.errorhandler(500)
def server_error(e):
    """#! Handle server errors."""
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
