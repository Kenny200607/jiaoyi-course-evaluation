"""Build only declared public source and a clean PyInstaller distribution."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import VERSION
from tools.audit_release import audit_tree

PUBLIC_FILES = (
    '.gitignore', '.gitattributes', '.env.example', 'app.py', 'logincopy.py',
    'browser_support.py', 'release_config.py', 'privacy.py', 'config.example.ini',
    'config/logincopy.config.example.json', 'README.md', 'LICENSE',
    'THIRD_PARTY_NOTICES.txt', 'CHANGELOG.md', '使用說明.txt',
    'requirements.txt', 'requirements-lock.txt', 'requirements-build.txt',
    'start_evaluation.cmd', 'CourseEvaluation.spec', '.github/workflows/checks.yml',
)


def public_files(root: Path) -> list[Path]:
    files = [root/name for name in PUBLIC_FILES]
    files += sorted((root/'tests').glob('test_*.py'))
    files += sorted((root/'tools').glob('*.py'))
    return files


def stage_source(root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for path in public_files(root):
        if not path.is_file():
            raise FileNotFoundError(f'Missing public source: {path.relative_to(root)}')
        target = destination/path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    info = source_provenance(root)
    info['source_files_sha256'] = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in public_files(root)}
    (destination/'SOURCE-INFO.json').write_text(json.dumps(info, indent=2), encoding='utf-8')


def source_provenance(root: Path) -> dict:
    if (root/'.git').exists():
        try:
            return {
                'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip(),
                'source_dirty': bool(subprocess.check_output(['git','status','--porcelain'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()),
            }
        except (OSError, subprocess.CalledProcessError):
            pass
    metadata = root/'SOURCE-INFO.json'
    if metadata.is_file():
        info = json.loads(metadata.read_text(encoding='utf-8'))
        hashes = info.get('source_files_sha256', {})
        edited = any(not (root/name).is_file() or hashlib.sha256((root/name).read_bytes()).hexdigest() != digest
                     for name, digest in hashes.items())
        return {'source_commit': info.get('source_commit'),
                'source_dirty': bool(info.get('source_dirty') or edited) if hashes else None}
    return {'source_commit': None, 'source_dirty': None}


def collect_notices(destination: Path) -> None:
    directory = destination/'third_party_licenses'
    directory.mkdir(exist_ok=True)
    inventory = []
    for distribution in sorted(importlib.metadata.distributions(), key=lambda item: item.metadata['Name'].lower()):
        name = distribution.metadata['Name']
        inventory.append({'name': name, 'version': distribution.version,
                          'license': distribution.metadata.get('License-Expression') or distribution.metadata.get('License', '')})
        for item in distribution.files or []:
            if any(word in item.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    target = directory/name/Path(str(item).replace('../',''))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix)/'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Python license missing; do not release the runtime without it.')
    shutil.copy2(python_license, directory/'Python-LICENSE.txt')
    (directory/'inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')


def archive_tree(directory: Path, archive: Path) -> None:
    errors = audit_tree(directory)
    if errors:
        raise RuntimeError('\n'.join(errors))
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                bundle.write(path, Path(directory.name)/path.relative_to(directory))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-only', action='store_true')
    args = parser.parse_args(argv)
    output = ROOT/'releases'
    output.mkdir(exist_ok=True)
    import tempfile
    staging_root = ROOT/'.release-work/staging'
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root, prefix='release-') as temporary:
        staging = Path(temporary)
        source = staging/f'JiaoyiCourseEvaluation-v{VERSION}-source'
        stage_source(ROOT, source)
        archives = [output/f'{source.name}.zip']
        archive_tree(source, archives[0])
        if not args.source_only:
            subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                            '--distpath', str(staging/'dist'), '--workpath', str(staging/'build'),
                            str(ROOT/'CourseEvaluation.spec')], cwd=ROOT, check=True)
            portable = staging/f'JiaoyiCourseEvaluation-v{VERSION}-windows-x64'
            shutil.copytree(staging/'dist/RunCourseEvaluation', portable)
            for name in ('config.example.ini', 'README.md', '使用說明.txt', 'LICENSE', 'THIRD_PARTY_NOTICES.txt', 'CHANGELOG.md'):
                shutil.copy2(ROOT/name, portable/name)
            shutil.copy2(ROOT/'config.example.ini', portable/'config.ini')
            collect_notices(portable)
            (portable/'BUILD-INFO.json').write_text(json.dumps({
                'version': VERSION, 'python': sys.version.split()[0],
                **source_provenance(ROOT),
                'requirements_sha256': hashlib.sha256((ROOT/'requirements-lock.txt').read_bytes()).hexdigest(),
            }, indent=2), encoding='utf-8')
            archives.append(output/f'{portable.name}.zip')
            archive_tree(portable, archives[-1])
        (output/'SHA256SUMS.txt').write_text(''.join(
            f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in archives), encoding='utf-8')
    for path in archives:
        print(path)


if __name__ == '__main__':
    main()
