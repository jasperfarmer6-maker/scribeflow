"""Copy a relocatable CPython runtime, dependencies and their original notices."""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess


def copy_ignore(directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in {'__pycache__', '.DS_Store', '_virtualenv.pth', '_virtualenv.py', 'direct_url.json'}
            or name.endswith(('.pyc', '.pyo')) or name.startswith(('_editable', '__editable__'))}


def verify_links(root: Path) -> None:
    resolved = root.resolve()
    for path in root.rglob('*'):
        if path.is_symlink():
            if os.path.isabs(os.readlink(path)) or not path.resolve().is_relative_to(resolved) or not path.exists():
                raise RuntimeError(f'Non-portable or broken symlink: {path.relative_to(root)}')


def copy_python(source: Path, target: Path) -> None:
    if not (source / 'bin/python3.12').is_file():
        raise RuntimeError('A standalone CPython 3.12 runtime is required')
    shutil.copytree(source, target, symlinks=True, ignore=copy_ignore)
    # These build-time tools have interpreter shebangs; the app needs only Python.
    for path in (target / 'bin').iterdir():
        if path.name not in {'python', 'python3', 'python3.12'}:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    verify_links(target)


def write_notices(resources: Path, site_packages: Path, notice: Path) -> None:
    destination = resources / 'Licenses'
    destination.mkdir()
    shutil.copy2(notice, destination / 'THIRD_PARTY_NOTICES.md')
    python_license = resources / 'runtime/python/lib/python3.12/LICENSE.txt'
    shutil.copy2(python_license, destination / 'Python-LICENSE.txt')
    supplemental = notice.parent / 'macos/ThirdPartyLicenses'
    if supplemental.is_dir():
        shutil.copytree(supplemental, destination / 'Supplemental')
    index = []
    for dist in sorted(importlib.metadata.distributions(path=[str(site_packages)]), key=lambda d: d.metadata['Name'].lower()):
        name = dist.metadata['Name']
        copied = []
        for file in dist.files or ():
            if not any(word in str(file).lower() for word in ('license', 'licence', 'copying', 'copyright', 'notice')):
                continue
            original = Path(dist.locate_file(file))
            if not original.is_file() or not original.resolve().is_relative_to(site_packages.resolve()):
                continue
            relative = original.relative_to(site_packages)
            target = destination / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            copied.append(str(target.relative_to(resources)))
        extra = destination / 'Supplemental' / name
        if extra.is_dir():
            copied.extend(str(p.relative_to(resources)) for p in extra.rglob('*') if p.is_file())
        index.append({'name': name, 'version': dist.version, 'license': dist.metadata.get('License-Expression') or dist.metadata.get('License', ''), 'files': copied})
    (destination / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')


def source_info(root: Path) -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
    return {'source_commit': git('rev-parse', 'HEAD'), 'source_dirty': bool(git('status', '--porcelain', '--untracked-files=normal'))}
