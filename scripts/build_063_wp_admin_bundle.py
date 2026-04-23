#!/usr/bin/env python3
from __future__ import annotations
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPO_ROOT = Path('/home/fwns6/code/wordpressyoshilover')
SRC_DIR = REPO_ROOT / 'src'
PLUGIN_FILE = SRC_DIR / 'yoshilover-063-frontend.php'
CUSTOM_CSS = SRC_DIR / 'custom.css'
CSS_START_MARKER = '.yoshi-topic-hub {'

def git_head() -> str:
    result = subprocess.run(['git', '-C', str(REPO_ROOT), 'rev-parse', '--short', 'HEAD'], check=True, capture_output=True, text=True)
    return result.stdout.strip()

def extract_css_section() -> str:
    text = CUSTOM_CSS.read_text(encoding='utf-8')
    start = text.find(CSS_START_MARKER)
    if start == -1:
        raise RuntimeError(f'Could not find CSS marker: {CSS_START_MARKER}')
    comment_start = text.rfind('/*', 0, start)
    if comment_start == -1:
        comment_start = start
    return text[comment_start:].lstrip()

def plugin_version() -> str:
    text = PLUGIN_FILE.read_text(encoding='utf-8')
    match = re.search(r'^\s*\*\s*Version:\s*([0-9.]+)\s*$', text, re.MULTILINE)
    if not match:
        raise RuntimeError('Could not find plugin version header')
    return match.group(1)

def build_dir_for_version(version: str) -> Path:
    parts = version.split('.')
    if len(parts) >= 2 and parts[1].isdigit():
        label = f'063-v{int(parts[1])}'
    else:
        label = '063-build'
    return REPO_ROOT / 'build' / f'{label}-wp-admin'

def build_plugin_zip(zip_path: Path) -> None:
    plugin_bytes = PLUGIN_FILE.read_bytes()
    with ZipFile(zip_path, 'w', compression=ZIP_DEFLATED) as zf:
        zf.writestr('yoshilover-063-frontend/yoshilover-063-frontend.php', plugin_bytes)

def write_manifest(css_path: Path, zip_path: Path) -> None:
    build_dir = zip_path.parent
    manifest = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'git_head': git_head(),
        'plugin_version': plugin_version(),
        'plugin_source': str(PLUGIN_FILE.relative_to(REPO_ROOT)),
        'css_source': str(CUSTOM_CSS.relative_to(REPO_ROOT)),
        'artifacts': {
            'plugin_zip': str(zip_path.relative_to(REPO_ROOT)),
            'css_snippet': str(css_path.relative_to(REPO_ROOT)),
        },
    }
    (build_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def main() -> None:
    version = plugin_version()
    build_dir = build_dir_for_version(version)
    build_dir.mkdir(parents=True, exist_ok=True)
    version_label = build_dir.name.replace('-wp-admin', '')
    css_path = build_dir / f'{version_label}-custom.css'
    zip_path = build_dir / 'yoshilover-063-frontend.zip'
    css_path.write_text(extract_css_section(), encoding='utf-8')
    build_plugin_zip(zip_path)
    write_manifest(css_path, zip_path)
    print(f'Built plugin zip: {zip_path}')
    print(f'Built CSS snippet: {css_path}')
    print(f'Wrote manifest: {build_dir / "manifest.json"}')

if __name__ == '__main__':
    main()
