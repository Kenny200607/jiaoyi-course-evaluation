"""Audit staged files without printing secret values."""
from __future__ import annotations
import argparse
import configparser
import json
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
        if name == '.env.example':
            try:
                allowed = {'USER_ID': {'', 'your_student_id'}, 'USER_PASSWORD': {'', 'your_password'}}
                for line in path.read_text(encoding='utf-8-sig').splitlines():
                    if '=' in line and not line.lstrip().startswith('#'):
                        key, value = line.split('=', 1)
                        if key.strip() in allowed and value.strip().strip('"').strip("'") not in allowed[key.strip()]:
                            errors.append(f'Populated credentials: {relative.as_posix()}')
                            break
            except UnicodeError:
                errors.append(f'Invalid public configuration: {relative.as_posix()}')
        if name == 'logincopy.config.example.json':
            try:
                config = json.loads(path.read_text(encoding='utf-8-sig'))
                if any(config.get('credentials', {}).get(key, '') for key in ('webvpn_username', 'webvpn_password')):
                    errors.append(f'Populated credentials: {relative.as_posix()}')
                if config.get('evaluation', {}).get('submit', False) is not False:
                    errors.append(f'Unsafe submission default: {relative.as_posix()}')
            except (ValueError, UnicodeError, AttributeError, TypeError):
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
