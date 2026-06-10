"""Compatibility audit for Huffman compression and decompression.

This script exercises the Flask API endpoints and reports whether the
round-trip restore is exact for a broad set of file types.
"""

import base64
import hashlib
import json
import sys
import uuid
import urllib.request
import zipfile
from pathlib import Path

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5000
URL_COMPRESS = f'http://{SERVER_HOST}:{SERVER_PORT}/compress'
URL_DECOMPRESS = f'http://{SERVER_HOST}:{SERVER_PORT}/decompress'

TEST_DIR = Path('tests')
TEST_DIR.mkdir(exist_ok=True)

JPEG_B64 = (
    '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDABALDA4MDRANDhAQEBQUGBQYFBUWGBQUHBwYGBgYI'  # noqa: E501
    'CAgICAgICAgICAgICAgICAgJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk/'
    '2wBDARESEhMUGBAUEhYVGRgYGCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJ'
    'CQkJCQkJCQkJCQkJCQkJCQkJ/3QAEAAf/2Q=='
)


def create_test_files():
    """Generate sample files for compatibility testing if they are missing."""
    files = {
        'sample.txt': b'Hello, Huffman world!\nThis is a sample text file.\n',
        'sample.json': b'{"message": "Hello", "count": 42}\n',
        'sample.csv': b'name,score\nAlice,100\nBob,95\n',
        'sample.xml': b'<root><item>Test</item></root>\n',
        'sample.pdf': None,
        'sample.png': None,
        'sample.jpg': base64.b64decode(JPEG_B64),
        'sample.mp4': None,
        'sample.docx': None,
        'sample.zip': None,
    }

    # preserve existing valid assets
    for name, content in files.items():
        path = TEST_DIR / name
        if path.exists():
            continue
        if content is not None:
            path.write_bytes(content)
            continue

        if name == 'sample.mp4':
            # Minimal MP4-like binary container header
            mp4_bytes = (
                b'\x00\x00\x00\x18ftypisom\x00\x00\x00\x01isomiso2avc1mp41'
                b'\x00\x00\x00\x10mdat\x00\x00\x00\x00\x00\x00\x00\x00'
            )
            path.write_bytes(mp4_bytes)
        elif name == 'sample.docx':
            docx_zip = zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED)
            docx_zip.writestr('[Content_Types].xml',
                              '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n</Types>\n')
            docx_zip.writestr('word/document.xml',
                              '<?xml version="1.0" encoding="UTF-8"?>\n<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Test</w:t></w:r></w:p></w:body></w:document>')
            docx_zip.writestr('_rels/.rels',
                              '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n</Relationships>\n')
            docx_zip.close()
        elif name == 'sample.zip':
            sample_zip = zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED)
            sample_zip.writestr('sample.txt', b'ZIP package sample content\n')
            sample_zip.close()

    # Ensure sample.png exists: do nothing if already present
    if not (TEST_DIR / 'sample.png').exists():
        (TEST_DIR / 'sample.png').write_bytes(base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottgAAAABJRU5ErkJggg=='
        ))

    if not (TEST_DIR / 'sample.pdf').exists():
        (TEST_DIR / 'sample.pdf').write_bytes(b'%PDF-1.4\n%EOF\n')


def build_multipart_form(filename, data, field_name='files', content_type='application/octet-stream'):
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
    lines = []
    lines.append(f'--{boundary}')
    lines.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"')
    lines.append(f'Content-Type: {content_type}')
    lines.append('')
    lines.append(data.decode('latin-1'))
    lines.append(f'--{boundary}--')
    lines.append('')
    body = '\r\n'.join(lines).encode('latin-1')
    headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
    return body, headers


def send_request(url, body, headers, timeout=120):
    req = urllib.request.Request(url, data=body, headers=headers)
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode('utf-8'))


def compute_sha256(data_bytes):
    hasher = hashlib.sha256()
    hasher.update(data_bytes)
    return hasher.hexdigest()


def run_audit():
    create_test_files()
    files_to_audit = [
        'sample.txt',
        'sample.json',
        'sample.csv',
        'sample.xml',
        'sample.jpg',
        'sample.png',
        'sample.mp4',
        'sample.pdf',
        'sample.docx',
        'sample.zip',
    ]

    report_rows = []
    for filename in files_to_audit:
        path = TEST_DIR / filename
        if not path.exists():
            print('Missing sample file:', filename)
            continue

        original_bytes = path.read_bytes()
        original_sha256 = compute_sha256(original_bytes)
        original_size = len(original_bytes)
        print(f'\nAUDIT {filename}: size={original_size}, sha256={original_sha256}')

        body, headers = build_multipart_form(filename, original_bytes)
        try:
            compress_resp = send_request(URL_COMPRESS, body, headers)
        except Exception as exc:
            print('  compress request failed:', exc)
            report_rows.append((filename, False, False, False, None, None, None, str(exc)))
            continue

        compress_result = compress_resp['results'][0]
        compress_success = compress_result.get('success', False)
        compressed_size = compress_result.get('compressed_size')
        compression_warning = compress_result.get('compression_warning')
        compression_ratio = compress_result.get('compression_ratio')
        compressed_filename = compress_result.get('compressed_filename')
        print('  compress response success=', compress_success)
        print('  compression_warning=', compression_warning)

        if not compress_success:
            report_rows.append((filename, False, False, False, original_size, compressed_size, compression_ratio, 'compress_failed'))
            continue

        compressed_zip_b64 = compress_result['data_b64']
        compressed_zip_bytes = base64.b64decode(compressed_zip_b64)
        compressed_zip_path = TEST_DIR / f'audit-{filename}-compressed.zip'
        compressed_zip_path.write_bytes(compressed_zip_bytes)

        body, headers = build_multipart_form(compressed_filename, compressed_zip_bytes, content_type='application/zip')
        try:
            decompress_resp = send_request(URL_DECOMPRESS, body, headers)
        except Exception as exc:
            print('  decompress request failed:', exc)
            report_rows.append((filename, True, False, False, original_size, compressed_size, compression_ratio, str(exc)))
            continue

        decompress_result = decompress_resp['results'][0]
        decompress_success = decompress_result.get('success', False)
        decompressed_sha256 = decompress_result.get('decompressed_sha256')
        integrity_verified = decompress_result.get('integrity_verified')
        print('  decompress response success=', decompress_success)
        print('  integrity_verified=', integrity_verified)

        if not decompress_success:
            report_rows.append((filename, True, False, False, original_size, compressed_size, compression_ratio, 'decompress_failed'))
            continue

        output_zip_bytes = base64.b64decode(decompress_result['data_b64'])
        output_zip_path = TEST_DIR / f'audit-{filename}-restored.zip'
        output_zip_path.write_bytes(output_zip_bytes)

        with zipfile.ZipFile(output_zip_path, 'r') as archive:
            members = [m for m in archive.namelist() if m != 'metadata.json']
            if not members:
                print('  restored ZIP has no payload member')
                report_rows.append((filename, True, True, False, original_size, compressed_size, compression_ratio, 'restored_payload_missing'))
                continue
            restored_name = members[0]
            restored_bytes = archive.read(restored_name)

        restored_sha256 = compute_sha256(restored_bytes)
        restored_size = len(restored_bytes)
        exact_match = restored_bytes == original_bytes
        print('  restored file:', restored_name)
        print('  restored size=', restored_size)
        print('  restored sha256=', restored_sha256)
        print('  exact_match=', exact_match)

        report_rows.append((filename, True, True, exact_match, original_size, compressed_size, compression_ratio, compression_warning or integrity_verified))

    print('\nCOMPATIBILITY AUDIT RESULTS')
    print('file,type compress,decompress,exact_match,orig_size,compressed_size,ratio,info')
    for row in report_rows:
        print(','.join(str(x) for x in row))

    if any(row[0] and not row[3] for row in report_rows):
        print('\nOne or more tests failed exact restoration.')
        sys.exit(1)
    print('\nAll audited files restored exactly.')


if __name__ == '__main__':
    run_audit()
