"""Run source in its own environment; leave global Python installations untouched."""
from pathlib import Path
import hashlib
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    if sys.version_info < (3, 12):
        print('Please install Python 3.12 or newer.')
        return 1
    environment = root/'.venv'
    python = environment/'Scripts/python.exe'
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(environment)], check=True)
    fingerprint = hashlib.sha256((root/'requirements-lock.txt').read_bytes()).hexdigest()
    marker = environment/'.requirements.sha256'
    if not marker.is_file() or marker.read_text().strip() != fingerprint:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root/'requirements-lock.txt')], cwd=root, check=True)
        marker.write_text(fingerprint, encoding='ascii')
    args = sys.argv[1:] or ['--pause']
    return subprocess.run([str(python), '-X', 'utf8', str(root/'app.py'), *args], cwd=root).returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print('Setup failed. Check Python and network availability:', exc, file=sys.stderr)
        raise SystemExit(1)
