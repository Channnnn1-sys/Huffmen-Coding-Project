"""
Huffman File Compression Web Application

Flask orchestration layer with native C++ Huffman compressor/decompressor.
The C++ binaries generate metadata JSON files which Flask forwards to clients.
"""

import base64
import json
import logging
import os
import platform
import re
import subprocess
import tempfile
import traceback
import zipfile
import time
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_file, abort, url_for
from werkzeug.utils import secure_filename

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
COMPRESSED_SUFFIX = "-compressed.bin"
BASE_DIR = Path(__file__).parent
COMPRESSOR_DIR = BASE_DIR / "compressor"
DOWNLOAD_ROOT = Path(os.environ.get("HUFFMAN_DOWNLOAD_DIR", tempfile.gettempdir())) / "huffman_downloads"
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
DOWNLOAD_EXPIRATION_SECONDS = 15 * 60

app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

# Helper functions

def get_compressor_binary(name):
    binary_name = f"huff{name}"
    custom_dir = os.environ.get("HUFFMAN_COMPRESSOR_DIR")
    compressor_dir = Path(custom_dir) if custom_dir else COMPRESSOR_DIR
    if platform.system() == "Windows":
        return (compressor_dir / f"{binary_name}.exe").resolve()
    return (compressor_dir / binary_name).resolve()

COMPRESS_EXE = get_compressor_binary("compress")
DECOMPRESS_EXE = get_compressor_binary("decompress")

app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


def safe_compressed_filename(filename):
    if filename.endswith(COMPRESSED_SUFFIX):
        return filename
    base, _ = os.path.splitext(filename)
    return f"{base}{COMPRESSED_SUFFIX}"


def build_response_archive_file(content_path, inner_filename, archive_name, metadata_paths, target_dir):
    archive_path = target_dir / archive_name
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(content_path, arcname=inner_filename)
        for metadata_path, arcname in metadata_paths:
            if metadata_path and metadata_path.exists():
                archive.write(metadata_path, arcname)
    return archive_path


def save_uploaded_file(file_storage, target_dir, filename=None):
    safe_name = secure_filename(filename or file_storage.filename)
    if not safe_name:
        raise ValueError("Uploaded file must have a filename")
    saved_path = target_dir / safe_name
    file_storage.save(str(saved_path))
    return saved_path


def load_json_file(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def cleanup_expired_downloads():
    now = time.time()
    for item in DOWNLOAD_ROOT.iterdir():
        try:
            if not item.is_dir():
                continue
            age = now - item.stat().st_mtime
            if age > DOWNLOAD_EXPIRATION_SECONDS:
                shutil.rmtree(item)
        except Exception as exc:
            logger.warning("Failed to cleanup expired download item %s: %s", item, exc)


def create_download_directory():
    download_token = uuid4().hex
    download_dir = DOWNLOAD_ROOT / download_token
    download_dir.mkdir(parents=True, exist_ok=False)
    return download_token, download_dir


def safe_download_path(token, filename):
    if not token or not filename:
        return None
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
        return download_path
    except Exception:
        return None


def log_directory_listing(path, context):
    try:
        entries = [child.name for child in path.iterdir()]
        logger.warning("%s contents: %s", context, entries)
    except Exception as exc:
        logger.warning("Failed to list %s: %s", context, exc)


def api_error_response(message, status=500):
    return jsonify({'error': message}), status


def startup_diagnostics():
    logger.info("BASE_DIR=%s", BASE_DIR)
    logger.info("COMPRESSOR_DIR=%s", COMPRESSOR_DIR)
    logger.info("COMPRESS_EXE=%s", COMPRESS_EXE)
    logger.info("DECOMPRESS_EXE=%s", DECOMPRESS_EXE)
    logger.info("cwd=%s", Path.cwd())
    logger.info("platform=%s", platform.platform())
    logger.info("system=%s", platform.system())
    logger.info("machine=%s", platform.machine())
    for exe, name in ((COMPRESS_EXE, 'compress'), (DECOMPRESS_EXE, 'decompress')):
        try:
            exists = exe.exists()
            is_file = exe.is_file()
            mode = oct(exe.stat().st_mode) if exists else 'n/a'
            executable = os.access(exe, os.X_OK) if exists else False
            logger.info("%s exists=%s is_file=%s executable=%s mode=%s", name.upper(), exists, is_file, executable, mode)
        except Exception as exc:
            logger.exception("Failed to inspect %s", exe)


def verify_compressor_binaries():
    logger.info("Verifying compressor binaries")
    missing = []
    for exe, name in ((COMPRESS_EXE, 'huffcompress'), (DECOMPRESS_EXE, 'huffdecompress')):
        try:
            if not exe.exists() or not exe.is_file():
                missing.append(str(exe))
                logger.error("Missing binary %s at %s", name, exe)
                continue
            if platform.system() != 'Windows' and not os.access(exe, os.X_OK):
                logger.warning("Binary not executable, attempting chmod: %s", exe)
                try:
                    os.chmod(exe, 0o755)
                except Exception as exc:
                    logger.exception("Failed to chmod %s", exe)
        except Exception:
            logger.error("Exception while verifying %s", exe)
            logger.error(traceback.format_exc())
            raise
    if missing:
        raise FileNotFoundError(f"Required compressor binaries missing: {', '.join(missing)}")


def initialize_startup():
    startup_diagnostics()
    verify_compressor_binaries()
    logger.info("Route initialization complete")


def safe_runner(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        logger.error("Startup exception in %s", func.__name__)
        logger.error(traceback.format_exc())
        raise


@app.before_request
def log_request_start():
    request_id = uuid4().hex[:8]
    request.environ['request_id'] = request_id
    logger.info("REQUEST START %s %s %s content_length=%s", request_id, request.method, request.path, request.content_length)
    if request.method == 'POST' and request.files:
        filenames = [secure_filename(upload.filename) for upload in request.files.getlist('files') if upload.filename]
        logger.info("REQUEST FILES %s %s", request_id, filenames)


@app.after_request
def log_request_end(response):
    request_id = request.environ.get('request_id', 'unknown')
    logger.info("REQUEST END %s %s %s %s", request_id, request.method, request.path, response.status)
    return response


def extract_compressed_bin_from_zip(zip_path, target_dir):
    try:
        with zipfile.ZipFile(zip_path, 'r') as archive:
            candidates = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                if name == 'metadata.json':
                    continue
                if name.endswith(COMPRESSED_SUFFIX) or name.lower().endswith('.bin'):
                    safe_name = secure_filename(name)
                    if not safe_name:
                        continue
                    candidates.append((info, safe_name))
            if len(candidates) != 1:
                return None, f"ZIP must contain exactly one compressed .bin file, found {len(candidates)}"
            info, safe_name = candidates[0]
            extracted_path = target_dir / safe_name
            with archive.open(info, 'r') as source, open(extracted_path, 'wb') as target:
                target.write(source.read())
            if not extracted_path.exists() or extracted_path.stat().st_size == 0:
                return None, "Failed to extract compressed .bin from ZIP"
            return extracted_path, None
    except zipfile.BadZipFile:
        return None, "Invalid ZIP archive"
    except Exception as exc:
        return None, f"Failed to extract ZIP contents: {exc}"


def find_subprocess_output(output_dir, expected_prefix):
    candidates = [path for path in output_dir.iterdir() if path.is_file() and path.name.startswith(expected_prefix)]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, f"Multiple output candidates found: {', '.join(path.name for path in candidates)}"
    return None, None


def maybe_timeout_for_size(filesize):
    if filesize > 50 * 1024 * 1024:
        logger.warning("Large upload detected: %s bytes; using extended timeout", filesize)
        return 120
    if filesize > 10 * 1024 * 1024:
        logger.warning("Medium upload detected: %s bytes; using longer timeout", filesize)
        return 60
    return 30


def run_compressor(input_file, exe_path, output_dir, timeout=30):
    operation = 'compress' if exe_path.name.lower().startswith('huffcompress') else 'decompress'
    if not exe_path.exists() or not exe_path.is_file():
        logger.error("Binary missing for %s: %s", operation, exe_path)
        return False, None, f"Compressor binary not found at: {exe_path}"
    if not input_file.exists():
        logger.error("Input file missing for %s: %s", operation, input_file)
        return False, None, f"Input file not found: {input_file}"
    if platform.system() != 'Windows':
        try:
            os.chmod(exe_path, 0o755)
        except Exception as exc:
            logger.warning("Could not chmod executable %s: %s", exe_path, exc)
    cmd = [str(exe_path), str(input_file)]
    start_time = time.monotonic()
    logger.info("Subprocess start %s: cmd=%s cwd=%s timeout=%s", operation, cmd, output_dir, timeout)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, kill_after=5, cwd=str(output_dir))
        elapsed = round(time.monotonic() - start_time, 3)
        logger.info("Subprocess end %s: returncode=%s elapsed=%ss", operation, result.returncode, elapsed)
        if result.returncode != 0:
            logger.warning("Subprocess %s failed returncode=%s stdout=%s stderr=%s", operation, result.returncode, result.stdout.strip(), result.stderr.strip())
            log_directory_listing(output_dir, f"{operation} output directory")
            return False, None, (result.stderr.strip() or result.stdout.strip() or 'Unknown error')
        if operation == 'compress':
            expected = output_dir / f"{input_file.stem}-compressed.bin"
            if not expected.exists():
                expected, err = find_subprocess_output(output_dir, f"{input_file.stem}-compressed")
                if err:
                    logger.warning("Compression output discovery failed: %s", err)
                    log_directory_listing(output_dir, "Compression output directory")
                    return False, None, err
        else:
            base_name = input_file.stem.replace('-compressed', '')
            candidates = [path for path in output_dir.iterdir() if path.is_file() and path.name.startswith(f"{base_name}-decompressed")]
            expected = None
            for candidate in candidates:
                if not candidate.name.lower().endswith('.json'):
                    expected = candidate
                    break
            if expected is None and candidates:
                expected = candidates[0]
            if expected is None:
                logger.warning("Decompressed output not found for %s", input_file.name)
                log_directory_listing(output_dir, "Decompression output directory")
                return False, None, f"Decompressed output not found for {input_file.name}"
        if not expected or not expected.exists() or expected.stat().st_size == 0:
            logger.warning("Output missing or empty after %s: %s", operation, expected)
            log_directory_listing(output_dir, f"{operation} expected output directory")
            return False, None, f"Output missing or empty: {expected}"
        return True, expected, None
    except subprocess.TimeoutExpired as exc:
        logger.warning("Subprocess timeout %s after %s seconds", operation, timeout)
        log_directory_listing(output_dir, f"{operation} timeout output directory")
        return False, None, f"Timeout after {timeout} seconds"
    except FileNotFoundError as exc:
        logger.exception("Executable not found: %s", exe_path)
        return False, None, f"Executable not found: {exc}"
    except Exception as exc:
        logger.exception("Unexpected subprocess error for %s", operation)
        log_directory_listing(output_dir, f"{operation} exception output directory")
        return False, None, f"Unexpected error: {exc}"


@app.route('/')
def home():
    try:
        return render_template('index.html')
    except Exception as e:
        print(traceback.format_exc())
        app.logger.error('Homepage rendering failed: %s', traceback.format_exc())
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/compress', methods=['GET', 'POST'])
def compress():
    if request.method == 'GET':
        return render_template('compress.html')
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files selected'}), 400
    results = []
    job_id = str(uuid4())[:8]
    cleanup_expired_downloads()
    with tempfile.TemporaryDirectory() as session_dir:
        session_path = Path(session_dir)
        for upload in files:
            if not upload.filename:
                continue
            filename = secure_filename(upload.filename)
            try:
                upload_size = getattr(upload, 'content_length', None)
                if upload_size and upload_size > app.config['MAX_CONTENT_LENGTH']:
                    results.append({'filename': filename, 'success': False, 'error': 'Upload exceeds allowed size'})
                    continue
                start_time = datetime.now()
                input_path = save_uploaded_file(upload, session_path, filename)
                if input_path.stat().st_size > app.config['MAX_CONTENT_LENGTH']:
                    results.append({'filename': filename, 'success': False, 'error': 'Upload exceeds allowed size'})
                    continue
                timeout = maybe_timeout_for_size(input_path.stat().st_size)
                success, output_path, error = run_compressor(input_path, COMPRESS_EXE, session_path, timeout=timeout)
                if not success:
                    results.append({'filename': filename, 'success': False, 'error': error})
                    continue
                metadata_path = output_path.with_name(f"{output_path.stem}-metadata.json")
                report_path = output_path.with_name(f"{output_path.stem}-compression_report.json")
                report_json = load_json_file(report_path)
                download_token, download_dir = create_download_directory()
                zip_name = f"{output_path.stem}-compressed.zip"
                archive_path = build_response_archive_file(output_path, output_path.name, zip_name, [(metadata_path, 'metadata.json'), (report_path, 'compression_report.json')], download_dir)
                download_url = url_for('download_file', token=download_token, filename=zip_name, _external=False)
                results.append({
                    'filename': filename,
                    'success': True,
                    'compressed_filename': zip_name,
                    'download_url': download_url,
                    'download_size': archive_path.stat().st_size,
                    'original_size': report_json.get('original_size', 0),
                    'compressed_size': report_json.get('compressed_size', 0),
                    'compression_ratio': report_json.get('compression_ratio', 0.0),
                    'saved_bytes': report_json.get('saved_bytes', 0),
                    'entropy': report_json.get('entropy', 0.0),
                    'entropy_warning': report_json.get('entropy_warning'),
                    'average_bits_per_symbol': report_json.get('average_bits_per_symbol', 0.0),
                    'efficiency_vs_8bit': report_json.get('efficiency_vs_8bit', 0.0),
                    'top_symbols': report_json.get('top_symbols', []),
                    'processing_time_seconds': round((datetime.now() - start_time).total_seconds(), 3)
                })
            except Exception as exc:
                logger.exception('Compression failed')
                results.append({'filename': filename, 'success': False, 'error': str(exc)})
    return jsonify({'job_id': job_id, 'results': results, 'timestamp': datetime.now().isoformat()})


@app.route('/decompress', methods=['GET', 'POST'])
def decompress():
    if request.method == 'GET':
        return render_template('decompress.html')
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files selected'}), 400
    results = []
    job_id = str(uuid4())[:8]
    cleanup_expired_downloads()
    with tempfile.TemporaryDirectory() as session_dir:
        session_path = Path(session_dir)
        for upload in files:
            if not upload.filename:
                continue
            filename = secure_filename(upload.filename)
            try:
                upload_size = getattr(upload, 'content_length', None)
                if upload_size and upload_size > app.config['MAX_CONTENT_LENGTH']:
                    results.append({'filename': filename, 'success': False, 'error': 'Upload exceeds allowed size'})
                    continue
                start_time = datetime.now()
                upload_path = save_uploaded_file(upload, session_path, filename)
                if upload_path.stat().st_size > app.config['MAX_CONTENT_LENGTH']:
                    results.append({'filename': filename, 'success': False, 'error': 'Upload exceeds allowed size'})
                    continue
                if upload_path.suffix.lower() == '.zip':
                    input_path, extract_error = extract_compressed_bin_from_zip(upload_path, session_path)
                    if extract_error:
                        results.append({'filename': filename, 'success': False, 'error': extract_error})
                        continue
                else:
                    safe_name = safe_compressed_filename(filename)
                    input_path = session_path / safe_name
                    if upload_path.name != input_path.name:
                        upload_path.rename(input_path)
                timeout = maybe_timeout_for_size(input_path.stat().st_size)
                success, output_path, error = run_compressor(input_path, DECOMPRESS_EXE, session_path, timeout=timeout)
                if not success:
                    results.append({'filename': filename, 'success': False, 'error': error})
                    continue
                metadata_path = output_path.with_name(f"{output_path.stem}-metadata.json")
                report_path = output_path.with_name(f"{output_path.stem}-decompression_report.json")
                report_json = load_json_file(report_path)
                download_token, download_dir = create_download_directory()
                zip_name = f"{output_path.stem}-decompressed.zip"
                archive_path = build_response_archive_file(output_path, output_path.name, zip_name, [(metadata_path, 'metadata.json'), (report_path, 'decompression_report.json')], download_dir)
                download_url = url_for('download_file', token=download_token, filename=zip_name, _external=False)
                results.append({
                    'filename': filename,
                    'success': True,
                    'decompressed_filename': zip_name,
                    'download_url': download_url,
                    'download_size': archive_path.stat().st_size,
                    'compressed_size': input_path.stat().st_size,
                    'decompressed_size': output_path.stat().st_size,
                    'processing_time_seconds': round((datetime.now() - start_time).total_seconds(), 3),
                    'report': report_json
                })
            except Exception as exc:
                logger.exception('Decompression failed')
                results.append({'filename': filename, 'success': False, 'error': str(exc)})
    return jsonify({'job_id': job_id, 'results': results, 'timestamp': datetime.now().isoformat()})


@app.route('/download/<token>/<path:filename>')
def download_file(token, filename):
    cleanup_expired_downloads()
    download_path = safe_download_path(token, filename)
    if not download_path or not download_path.exists() or not download_path.is_file():
        logger.warning('Download file not found: token=%s filename=%s', token, filename)
        return api_error_response('Download file not found', 404)
    try:
        return send_file(str(download_path), as_attachment=True, download_name=download_path.name, mimetype='application/zip')
    except Exception as exc:
        logger.exception('Download failed for %s/%s', token, filename)
        return api_error_response('Download failed', 500)


@app.route('/debug')
def debug():
    return jsonify({
        'platform': platform.system(),
        'compressor_dir': str(COMPRESSOR_DIR),
        'compress_exe': str(COMPRESS_EXE),
        'decompress_exe': str(DECOMPRESS_EXE)
    })


@app.route('/health')
def health():
    return {
        'status': 'ok',
        'cwd': str(Path.cwd()),
        'compress_exists': COMPRESS_EXE.exists(),
        'decompress_exists': DECOMPRESS_EXE.exists(),
        'compress_path': str(COMPRESS_EXE),
        'decompress_path': str(DECOMPRESS_EXE),
    }


@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum size is 100MB'}), 413


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Page not found'}), 404


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.exception('Unhandled exception during request %s %s', request.method, request.path)
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    try:
        safe_runner(initialize_startup)
    except Exception:
        logger.error('Application startup failed. Exiting.')
        raise SystemExit(1)
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception:
        logger.error('Flask startup failed')
        logger.error(traceback.format_exc())
        raise SystemExit(1)
