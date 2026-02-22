from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
min_lines = 500

IGNORED_DIRS = {'.venv', 'venv', 'env', 'node_modules', '.git', '__pycache__'}

files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    # modify dirnames in-place to skip ignored directories
    dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
    for fn in filenames:
        if fn.endswith('.py'):
            p = Path(dirpath) / fn
            try:
                with p.open('rb') as f:
                    lines = sum(1 for _ in f)
            except Exception as e:
                print(f"SKIP {p}: {e}")
                continue
            files.append((str(p.relative_to(ROOT)), lines))

files = sorted(files, key=lambda x: x[1], reverse=True)

print('Files with more than', min_lines, 'lines:')
for path, count in files:
    if count > min_lines:
        print(f"{count:6d}  {path}")

print('\nTotal .py files scanned:', len(files))
