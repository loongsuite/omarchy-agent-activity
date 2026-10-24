#!/usr/bin/env python3
"""Stage our runtime only; no Pilot source, node_modules or personal data."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

source = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
runtime = ['BarWidget.qml', 'Panel.qml', 'SetupView.qml', 'UsageDashboard.qml',
           'SessionBrowser.qml', 'bin/pilot_snapshot.py', 'bin/pilot_setup.py']
h = hashlib.sha256()
for name in runtime:
    h.update(name.encode() + b'\0' + (source / name).read_bytes())
release = Path('releases') / h.hexdigest()[:16]
for name in runtime:
    dest = target / release / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / name, dest)
for name in ['LICENSE', 'README.md']:
    shutil.copy2(source / name, target / name)
manifest = json.loads((source / 'manifest.json').read_text())
manifest['entryPoints']['barWidget'] = str(release / 'BarWidget.qml')
(target / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Staged', release)
