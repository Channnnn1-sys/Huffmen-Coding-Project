import base64, json, urllib.request, uuid, zipfile, hashlib, sys
from pathlib import Path

root = Path('tests')
root.mkdir(exist_ok=True)

# Ensure sample.png is valid PNG bytes
png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMA AAsJTYQAAAAASUVORK5CYII='
png_b64 = png_b64.replace(' ', '')
if (root / 'sample.png').stat().st_size == 0:
    (root / 'sample.png').write_bytes(base64.b64decode(png_b64))

tests = [
    'sample.txt',
    'sample.csv',
    'sample.png',
    'sample.pdf',
    'file with spaces.txt'
]

URL_COMPRESS = 'http://127.0.0.1:5000/compress'
URL_DECOMPRESS = 'http://127.0.0.1:5000/decompress'

boundary = '----WebKitFormBoundary' + uuid.uuid4().hex
headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}

all_ok = True

for name in tests:
    path = root / name
    if not path.exists():
        print('MISSING', path)
        all_ok = False
        continue
    orig_bytes = path.read_bytes()
    orig_hash = hashlib.sha256(orig_bytes).hexdigest()
    print('\nTEST', name, 'orig_sha256', orig_hash)

    # build multipart for compress
    lines = []
    lines.append(f'--{boundary}')
    lines.append(f'Content-Disposition: form-data; name="files"; filename="{name}"')
    lines.append('Content-Type: application/octet-stream')
    lines.append('')
    lines.append(orig_bytes.decode('latin-1'))
    lines.append(f'--{boundary}--')
    lines.append('')
    body = '\r\n'.join(lines).encode('latin-1')

    req = urllib.request.Request(URL_COMPRESS, data=body, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except Exception as e:
        print('COMPRESS ERROR', e)
        all_ok = False
        continue
    resp_json = json.loads(resp.read().decode('utf-8'))
    success = resp_json['results'][0].get('success')
    if not success:
        print('COMPRESS FAILED', resp_json)
        all_ok = False
        continue
    zip_b64 = resp_json['results'][0]['data_b64']
    zip_name = resp_json['results'][0]['compressed_filename']
    zip_path = root / zip_name
    zip_path.write_bytes(base64.b64decode(zip_b64))
    print('compressed zip', zip_path)

    # send zip to decompress
    lines = []
    lines.append(f'--{boundary}')
    lines.append(f'Content-Disposition: form-data; name="files"; filename="{zip_name}"')
    lines.append('Content-Type: application/zip')
    lines.append('')
    lines.append(zip_path.read_bytes().decode('latin-1'))
    lines.append(f'--{boundary}--')
    lines.append('')
    body = '\r\n'.join(lines).encode('latin-1')

    req = urllib.request.Request(URL_DECOMPRESS, data=body, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except Exception as e:
        print('DECOMPRESS ERROR', e)
        all_ok = False
        continue
    resp_json = json.loads(resp.read().decode('utf-8'))
    success = resp_json['results'][0].get('success')
    if not success:
        print('DECOMPRESS FAILED', resp_json)
        all_ok = False
        continue
    out_b64 = resp_json['results'][0]['data_b64']
    out_name = resp_json['results'][0]['decompressed_filename']
    out_path = root / out_name
    out_path.write_bytes(base64.b64decode(out_b64))
    print('decompressed zip', out_path)

    with zipfile.ZipFile(out_path, 'r') as zf:
        members = [m for m in zf.namelist() if m != 'metadata.json']
        if not members:
            print('NO MEMBERS IN OUT ZIP')
            all_ok = False
            continue
        extracted = zf.extract(members[0], path=root)
    restored_bytes = Path(extracted).read_bytes()
    restored_hash = hashlib.sha256(restored_bytes).hexdigest()
    print('restored_sha256', restored_hash)
    ok = orig_hash == restored_hash
    print('PASS' if ok else 'FAIL')
    if not ok:
        all_ok = False

print('\nSUMMARY OK=' + str(all_ok))
if not all_ok:
    sys.exit(2)
else:
    sys.exit(0)
