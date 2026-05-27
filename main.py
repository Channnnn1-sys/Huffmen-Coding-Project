"""
Huffman File Compression Web Application
A Flask-based web application for file compression/decompression using Huffman coding.
Supports batch processing of multiple files with drag-and-drop upload UI.
Cloud-native stateless implementation for Render/Linux deployment.
"""

import os
import sys
import io
import re
import zipfile
import logging
import subprocess
import tempfile
import platform
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from collections import Counter
from math import log2
import json
import base64
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, send_file, jsonify

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

app = Flask(__name__)

# Security and upload configuration
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max upload

# File type restrictions
# Note: The project now accepts arbitrary file types. Extension-based
# whitelisting was removed to support binary and non-text payloads.
# Empty-file validation is still performed at runtime.

# Analysis constants
ZIP_BASED_OFFICE_EXTENSIONS = {"docx", "pptx", "xlsx"}
HIGH_ENTROPY_WARNING_EXTENSIONS = {
    "zip", "rar", "7z",
    "jpg", "jpeg", "png", "gif",
    "mp4", "mp3", "pdf"
}
SAMPLED_ENTROPY_BYTES = 100 * 1024
HIGH_ENTROPY_THRESHOLD = 7.3
COMPRESSED_SUFFIX = "-compressed.bin"

# Directory paths
BASE_DIR = Path(__file__).parent
COMPRESSOR_DIR = BASE_DIR / "compressor"

# Detect platform and set binary names
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
    
    # Allow custom compressor directory via environment variable
    custom_dir = os.environ.get("HUFFMAN_COMPRESSOR_DIR")
    if custom_dir:
        compressor_dir = Path(custom_dir)
    else:
        compressor_dir = COMPRESSOR_DIR
    
    # On Windows, add .exe extension
    if platform.system() == "Windows":
        binary_path = compressor_dir / f"{binary_name}.exe"
    else:
        binary_path = compressor_dir / binary_name
    
    return binary_path.resolve()

COMPRESS_EXE = get_compressor_binary("compress")
DECOMPRESS_EXE = get_compressor_binary("decompress")

logger.info(f"Platform: {platform.system()}")
logger.info(f"Base directory: {BASE_DIR}")
logger.info(f"Compressor directory: {COMPRESSOR_DIR}")
logger.info(f"Compress binary: {COMPRESS_EXE}")
logger.info(f"Decompress binary: {DECOMPRESS_EXE}")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def allowed_file(filename, operation="compress"):
    """Allow any filename (remove extension whitelist).

    This preserves a single responsibility: check that a filename
    was supplied. Actual content validation (empty file, corrupted
    ZIP, compressor errors) is handled during processing.
    """
    return bool(filename and filename.strip())


def get_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


def compute_entropy(byte_sequence):
    """Estimate Shannon entropy in bits per byte."""
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
    """Return a mapping of byte values to Huffman code lengths."""
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
    """Inspect Office ZIP containers and report text/XML layer metrics."""
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
        logger.warning(f"Office deep scan failed: {err}")
        details["office_message"] = "Office deep scan encountered an error during content analysis."

    return details


def create_compression_report(path, compressed_size, sample_limit=1024 * 1024):
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
    ext = get_extension(filename)
    warnings = []
    if ext in HIGH_ENTROPY_WARNING_EXTENSIONS:
        warnings.append("This file type is often already compressed or contains binary data.")
    if entropy >= HIGH_ENTROPY_THRESHOLD:
        warnings.append(
            "Entropy analysis indicates a high degree of randomness. Additional Huffman compression may not significantly reduce file size."
        )
    return " ".join(warnings) if warnings else None


def format_warning_text(warning):
    return warning if warning else ""


def safe_compressed_filename(filename):
    if filename.endswith(COMPRESSED_SUFFIX):
        return filename
    base, ext = os.path.splitext(filename)
    return f"{base}{COMPRESSED_SUFFIX}"


def safe_decompressed_filename(filename, extension=""):
    base = filename
    if filename.endswith(COMPRESSED_SUFFIX):
        base = filename[:-len(COMPRESSED_SUFFIX)]
    elif filename.lower().endswith('.bin'):
        base = filename[:-4]
    return f"{base}-decompressed{extension}"


def maybe_timeout_for_size(filesize):
    if filesize > 50 * 1024 * 1024:
        return 120
    if filesize > 10 * 1024 * 1024:
        return 60
    return 30


def run_compressor(input_file, exe_path, output_dir, timeout=30):
    """
    Execute compressor/decompressor with comprehensive error handling and logging.
    Uses temporary directory and returns output file path.
    
    Args:
        input_file: Path to input file
        exe_path: Path to executable (huffcompress or huffdecompress)
        output_dir: Temporary directory to store output
        timeout: Process timeout in seconds
        
    Returns:
        (success: bool, output_file: Path|None, error_message: str|None)
    """
    operation = "compress" if "compress" in exe_path.name.lower() and "decompress" not in exe_path.name.lower() else "decompress"
    
    logger.info(f"Starting {operation} operation")
    logger.info(f"  Input file: {input_file}")
    logger.info(f"  Input file size: {input_file.stat().st_size if input_file.exists() else 'N/A'} bytes")
    logger.info(f"  Executable: {exe_path}")
    logger.info(f"  Executable exists: {exe_path.exists()}")
    logger.info(f"  Output directory: {output_dir}")
    logger.info(f"  Current working directory: {os.getcwd()}")
    
    try:
        # Check if executable exists
        if not exe_path.exists():
            error_msg = (
                f"Compressor binary not found at: {exe_path}\n"
                f"Platform: {platform.system()}\n"
                f"Compressor directory contents: {list(COMPRESSOR_DIR.glob('*'))}"
            )
            logger.error(error_msg)
            return False, None, error_msg
        
        # Verify input file exists
        if not input_file.exists():
            error_msg = f"Input file not found: {input_file}"
            logger.error(error_msg)
            return False, None, error_msg
        
        # Make executable on Unix systems
        if platform.system() != "Windows":
            try:
                current_mode = exe_path.stat().st_mode
                logger.info(f"  Executable current permissions: {oct(current_mode)}")
                os.chmod(exe_path, 0o755)
                logger.info(f"  Executable permissions set to: 0o755")
            except Exception as e:
                logger.warning(f"Could not set executable permissions: {e}")
        
        # Run subprocess with proper error handling
        logger.info(f"Running command: {exe_path} {input_file}")
        result = subprocess.run(
            [str(exe_path), str(input_file)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(output_dir)
        )

        logger.info(f"  Return code: {result.returncode}")
        if result.stdout:
            logger.info(f"  Stdout: {result.stdout[:200]}")
        if result.stderr:
            logger.warning(f"  Stderr: {result.stderr[:200]}")

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else (result.stdout.strip() or "Unknown error")
            error_full = (
                f"Compressor returned error code {result.returncode}:\n"
                f"  Error: {error_msg}\n"
                f"  Command: {exe_path} {input_file}\n"
                f"  Working directory: {output_dir}"
            )
            logger.error(error_full)
            return False, None, error_full

        # Determine output filename based on operation
        if operation == "compress":
            # Compression: input_file -> input_file-compressed.bin
            expected_output = input_file.parent / f"{input_file.stem}-compressed.bin"
            logger.info(f"  Expected output file: {expected_output.name}")
        else:
            # Decompression: output depends on original extension (embedded in .bin)
            # Expected pattern: input_file-decompressed.EXT
            base_name = input_file.stem.replace("-compressed", "")
            expected_output = None
            
            # Search for decompressed output file
            logger.info(f"  Searching for decompressed output file with base name: {base_name}")
            for candidate in output_dir.iterdir():
                if candidate.is_file() and candidate.name.startswith(base_name + "-decompressed"):
                    expected_output = candidate
                    logger.info(f"  Found decompressed file: {candidate.name}")
                    break
            
            if expected_output is None:
                files_in_dir = [f.name for f in output_dir.iterdir() if f.is_file()]
                error_msg = (
                    f"Decompressed output file not found for input: {input_file.name}\n"
                    f"  Base name: {base_name}\n"
                    f"  Files in output directory: {files_in_dir}"
                )
                logger.error(error_msg)
                return False, None, error_msg

        if expected_output.exists():
            output_size = expected_output.stat().st_size
            logger.info(f"  ✓ {operation.capitalize()} successful: {expected_output.name} ({output_size} bytes)")
            return True, expected_output, None
        else:
            error_msg = (
                f"Output file not found after {operation}: {expected_output.name}\n"
                f"  Expected path: {expected_output}\n"
                f"  Files in output directory: {list(output_dir.glob('*'))}"
            )
            logger.error(error_msg)
            return False, None, error_msg

    except subprocess.TimeoutExpired:
        error_msg = f"Compression timeout after {timeout} seconds"
        logger.error(error_msg)
        return False, None, error_msg
    except FileNotFoundError as e:
        error_msg = f"Executable not found: {str(e)}"
        logger.error(error_msg)
        return False, None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error during {operation}: {str(e)}"
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
    GET: Render compression form
    POST: Process uploaded files and stream results without persistent storage
    
    Returns JSON with download URLs for each compressed file.
    """
    if request.method == "GET":
        return render_template("compress.html")

    # POST request - process files
    logger.info("POST /compress received request")
    if "files" not in request.files:
        logger.warning("POST /compress missing files field")
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    logger.info("POST /compress received %d file(s)", len(files))
    if not files or len(files) == 0:
        return jsonify({"error": "No files selected"}), 400

    # Generate unique job ID
    job_id = generate_job_id()
    results = []

    # Create a temporary directory for this batch of operations
    with tempfile.TemporaryDirectory() as temp_session_dir:
        temp_session_path = Path(temp_session_dir)

        for file in files:
            if file.filename == "":
                continue

            if not allowed_file(file.filename, "compress"):
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "Unsupported file type. Please upload a valid file."
                })
                continue

            filename = secure_filename(file.filename)
            temp_input_path = temp_session_path / filename
            
            try:
                start_time = datetime.now()
                # Save uploaded file temporarily
                file.save(str(temp_input_path))

                original_size = temp_input_path.stat().st_size
                sample_bytes = sample_file_bytes(temp_input_path)
                entropy_value = compute_entropy(sample_bytes)
                entropy_warning = make_entropy_warning(filename, entropy_value)
                office_scan = analyze_office_archive(temp_input_path)

                # Run compression with a timeout adapted to file size
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

                # Read compressed file into memory
                with open(output_file, "rb") as f:
                    compressed_data = f.read()

                compressed_size = len(compressed_data)
                processing_time = (datetime.now() - start_time).total_seconds()
                report = create_compression_report(temp_input_path, compressed_size)

                # Create ZIP containing compressed data and metadata
                zip_name = f"{temp_input_path.stem}-compressed.zip"
                zip_path = temp_session_path / zip_name
                metadata = {
                    "algorithm": "huffman",
                    "original_filename": filename,
                    "original_size": report["original_size"],
                    "compressed_filename": output_file.name,
                    "compressed_size": report["compressed_size"],
                    "timestamp": datetime.now().isoformat()
                }
                try:
                    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr(output_file.name, compressed_data)
                        zf.writestr('metadata.json', json.dumps(metadata))

                    with open(zip_path, 'rb') as zf:
                        zip_bytes = zf.read()

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
                        "data_b64": base64.b64encode(zip_bytes).decode()
                    })
                except Exception as e:
                    logger.exception("Failed to create ZIP for compressed output")
                    results.append({
                        "filename": filename,
                        "success": False,
                        "error": f"Failed to create ZIP: {e}"
                    })

            except Exception as e:
                logger.exception("Unexpected error during compression")
                results.append({
                    "filename": filename,
                    "success": False,
                    "error": str(e)
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
    GET: Render decompression form
    POST: Process uploaded .bin files and stream results without persistent storage

    Returns JSON with download URLs for each decompressed file.
    """
    if request.method == "GET":
        return render_template("decompress.html")

    logger.info("POST /decompress received request")
    if "files" not in request.files:
        logger.warning("POST /decompress missing files field")
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    logger.info("POST /decompress received %d file(s)", len(files))
    if not files or len(files) == 0:
        return jsonify({"error": "No files selected"}), 400

    # Generate unique job ID
    job_id = generate_job_id()
    results = []

    # Create a temporary directory for this batch of operations
    with tempfile.TemporaryDirectory() as temp_session_dir:
        temp_session_path = Path(temp_session_dir)

        for file in files:
            if file.filename == "":
                continue

            filename = secure_filename(file.filename)

            if not allowed_file(file.filename, "decompress"):
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "Unsupported file type. Please upload a valid .bin file generated by this tool."
                })
                continue

            # Save uploaded file temporarily (support .zip containing compressed .bin)
            temp_upload_path = temp_session_path / filename

            try:
                start_time = datetime.now()
                # Save uploaded file temporarily
                file.save(str(temp_upload_path))

                # If uploaded ZIP, extract contained compressed .bin
                ext = get_extension(filename)
                if ext == 'zip':
                    try:
                        with zipfile.ZipFile(temp_upload_path, 'r') as zf:
                            candidate = None
                            for info in zf.infolist():
                                if info.filename.endswith('-compressed.bin') or info.filename.lower().endswith('.bin'):
                                    candidate = info.filename
                                    break
                            if candidate is None:
                                results.append({
                                    "filename": filename,
                                    "success": False,
                                    "error": "No compressed .bin file found inside uploaded ZIP"
                                })
                                continue

                            zf.extract(candidate, path=str(temp_session_path))
                            temp_input_path = temp_session_path / candidate
                    except zipfile.BadZipFile:
                        results.append({
                            "filename": filename,
                            "success": False,
                            "error": "Uploaded ZIP is invalid or corrupted"
                        })
                        continue
                else:
                    # Ensure the decompressor sees a safe compressed filename
                    safe_filename = safe_compressed_filename(filename)
                    temp_input_path = temp_session_path / safe_filename
                    if temp_upload_path.exists() and temp_upload_path.name != temp_input_path.name:
                        temp_upload_path.rename(temp_input_path)

                # Run decompression with a timeout adapted to the uploaded file size
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

                # Read decompressed file into memory
                with open(output_file, "rb") as f:
                    decompressed_data = f.read()

                # Get file sizes
                compressed_size = temp_input_path.stat().st_size
                decompressed_size = len(decompressed_data)
                processing_time = (datetime.now() - start_time).total_seconds()

                # Create ZIP containing decompressed data and metadata
                zip_name = f"{Path(output_file).stem}-decompressed.zip"
                zip_path = temp_session_path / zip_name
                metadata = {
                    "algorithm": "huffman",
                    "original_compressed": filename,
                    "decompressed_filename": output_file.name,
                    "compressed_size": compressed_size,
                    "decompressed_size": decompressed_size,
                    "timestamp": datetime.now().isoformat()
                }
                try:
                    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr(output_file.name, decompressed_data)
                        zf.writestr('metadata.json', json.dumps(metadata))

                    with open(zip_path, 'rb') as zf:
                        zip_bytes = zf.read()

                    results.append({
                        "filename": filename,
                        "success": True,
                        "decompressed_filename": zip_name,
                        "compressed_size": compressed_size,
                        "decompressed_size": decompressed_size,
                        "processing_time_seconds": round(processing_time, 3),
                        "data_b64": base64.b64encode(zip_bytes).decode()
                    })
                except Exception as e:
                    logger.exception("Failed to create ZIP for decompressed output")
                    results.append({
                        "filename": filename,
                        "success": False,
                        "error": f"Failed to create ZIP: {e}"
                    })

            except Exception as e:
                results.append({
                    "filename": filename,
                    "success": False,
                    "error": str(e)
                })

    return jsonify({
        "job_id": job_id,
        "results": results,
        "timestamp": datetime.now().isoformat()
    })


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
