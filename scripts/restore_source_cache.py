"""Restore only dated SHFE official JSON reports from the public bootstrap archive."""
import json
from pathlib import Path
import re
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
with zipfile.ZipFile(sys.argv[1]) as archive:
    entries = archive.infolist()
    if len(entries) > 1000 or sum(e.file_size for e in entries) > 100_000_000:
        raise ValueError('Unexpected bootstrap archive size.')
    payloads = []
    for entry in entries:
        match = re.fullmatch(r'data/raw/(kx|pm)(\d{8})\.dat', entry.filename)
        if not match:
            raise ValueError('Unexpected bootstrap filename.')
        raw = archive.read(entry)
        doc = json.loads(raw)
        field = 'o_curinstrument' if match[1] == 'kx' else 'o_cursor'
        if doc.get('report_date') != match[2] or not doc.get(field):
            raise ValueError('Bootstrap report date/content mismatch.')
        payloads.append((entry.filename, raw))
    for name, raw in payloads:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(raw)
print(f'Restored {len(payloads)} validated official historical reports.')
