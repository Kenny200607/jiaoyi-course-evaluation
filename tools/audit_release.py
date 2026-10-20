"""Audit staged files without printing secret values."""
from __future__ import annotations
import argparse
import configparser
from pathlib import Path
from urllib.parse import quote


def audit_tree(root: Path, secrets=()) -> list[str]:
    errors = []
    forbidden_parts = {'.git', '.env', '.release-work', '.venv', '__pycache__', '.browser-profile', 'logs', 'downloads', 'screenshots'}
    patterns = []
    for value in secrets:
        if value:
            patterns.extend((value.encode('utf-8'), value.encode('utf-16-le'), quote(value, safe='').encode()))
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        name = path.name.lower()
        if (any(part.lower() in forbidden_parts for part in relative.parts)
                or name in {'cookies.json', 'credentials.local.json', 'config.local.json', 'logincopy.config.json'}
                or name.endswith('.log') or name.startswith('.env') and name != '.env.example'):
            errors.append(f'Private file: {relative.as_posix()}')
        if name in {'config.ini', 'config.example.ini'}:
            try:
                parser = configparser.ConfigParser(interpolation=None)
                parser.read_string(path.read_text(encoding='utf-8-sig'))
                if any(parser.get('user-account', key, fallback='').strip() for key in ('username','password')):
                    errors.append(f'Populated credentials: {relative.as_posix()}')
                if parser.getboolean('evaluation-option', 'submit', fallback=False):
                    errors.append(f'Unsafe submission default: {relative.as_posix()}')
            except (configparser.Error, UnicodeError, ValueError):
                errors.append(f'Invalid public configuration: {relative.as_posix()}')
        content = path.read_bytes()
        if any(pattern in content for pattern in patterns):
            errors.append(f'Private value detected: {relative.as_posix()}')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    errors = audit_tree(args.directory)
    for error in errors:
        print(error)
    print('PASS' if not errors else 'FAIL')
    raise SystemExit(bool(errors))
