"""Installed Chrome/Edge detection and native Windows file-version lookup."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path


def browser_name(config: dict) -> str:
    name = config.get('driver', 'Chrome')
    if not isinstance(name, str) or name.lower() not in ('chrome', 'edge'):
        raise ValueError('瀏覽器只支援 Chrome 或 Edge。')
    return name.capitalize()


def find_browser(config: dict, roots=None) -> str | None:
    name = browser_name(config)
    explicit = config.get('chrome_binary')
    if explicit:
        if not Path(explicit).is_file():
            raise ValueError('找不到指定的瀏覽器程式。')
        return str(Path(explicit).resolve())
    if roots is None:
        roots = [Path(os.environ.get(key, fallback)) for key, fallback in (
            ('PROGRAMFILES', r'C:\Program Files'),
            ('PROGRAMFILES(X86)', r'C:\Program Files (x86)'),
            ('LOCALAPPDATA', str(Path.home()/'AppData/Local')),
        )]
    suffix = 'Google/Chrome/Application/chrome.exe' if name == 'Chrome' else 'Microsoft/Edge/Application/msedge.exe'
    for root in roots:
        path = Path(root)/suffix
        if path.is_file():
            return str(path)
    return None


def file_version(path: str | Path | None) -> str | None:
    if not path:
        return None
    try:
        from ctypes import wintypes
        version = ctypes.WinDLL('version', use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
        length = version.GetFileVersionInfoSizeW(str(path), None)
        if not length:
            return None
        buffer = ctypes.create_string_buffer(length)
        if not version.GetFileVersionInfoW(str(path), 0, length, buffer):
            return None
        info, size = ctypes.c_void_p(), wintypes.UINT()
        if not version.VerQueryValueW(buffer, '\\', ctypes.byref(info), ctypes.byref(size)) or size.value < 16:
            return None
        values = ctypes.cast(info, ctypes.POINTER(wintypes.DWORD))
        return '.'.join(map(str, (values[2] >> 16, values[2] & 0xffff, values[3] >> 16, values[3] & 0xffff)))
    except (AttributeError, OSError, ValueError):
        return None


def versions_match(browser: str, browser_version: str, driver_version: str) -> bool:
    count = 3 if browser == 'Edge' else 1
    browser_parts, driver_parts = browser_version.split('.'), driver_version.split('.')
    return len(browser_parts) >= count and len(driver_parts) >= count and browser_parts[:count] == driver_parts[:count]
