"""Public INI configuration; no implicit secret fallback from an explicit file."""
from __future__ import annotations

import configparser
import copy
import json
import sys
from pathlib import Path


class FirstRunConfig(Exception):
    """A blank configuration was created; no browser should be started yet."""


def app_directory() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _dotenv(path: Path) -> dict:
    result = {}
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _ini(path: Path, config: dict) -> dict:
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=None)
    try:
        parser.read_string(path.read_text(encoding='utf-8-sig'))
    except (configparser.Error, UnicodeError):
        raise ValueError('設定檔格式錯誤；請使用 UTF-8 的 INI 格式。') from None
    allowed = {
        'user-account': {'username', 'password'},
        'browser-option': {'driver', 'exe_path', 'driver_path'},
        'evaluation-option': {'submit', 'max_courses', 'dry_run_limit'},
        'script-option': {'headless', 'close_browser_on_finish'},
    }
    if parser.defaults() or any(section not in allowed for section in parser.sections()):
        raise ValueError('設定檔含未知區段；請參考 config.example.ini。')
    for section in parser.sections():
        if set(parser[section]) - allowed[section]:
            raise ValueError('設定檔含未知選項；請參考 config.example.ini。')
    get = lambda section, key, default='': parser.get(section, key, fallback=default)
    config['credentials'] = {
        'webvpn_username': get('user-account', 'username'),
        'webvpn_password': get('user-account', 'password'),
    }
    config['browser'].update(
        driver=get('browser-option', 'driver', 'Chrome'),
        chrome_binary=get('browser-option', 'exe_path'),
        chromedriver_path=get('browser-option', 'driver_path'),
    )
    try:
        config['evaluation'].update(
            submit=parser.getboolean('evaluation-option', 'submit', fallback=False),
            maxCourses=parser.getint('evaluation-option', 'max_courses', fallback=0),
            dryRunLimit=parser.getint('evaluation-option', 'dry_run_limit', fallback=1),
        )
        for key in ('headless', 'close_browser_on_finish'):
            config['download'][key] = parser.getboolean('script-option', key, fallback=False)
    except ValueError:
        raise ValueError('設定中的開關須為 true/false，課程數須為整數。') from None
    return config


def validate_config(config: dict, base_dir: Path) -> dict:
    try:
        credentials = config['credentials']
        values = [credentials.get(key, '') for key in ('webvpn_username', 'webvpn_password')]
        if not all(isinstance(value, str) for value in values) or bool(values[0]) != bool(values[1]):
            raise ValueError('帳號及密碼請同時填寫，或同時留空以手動登入。')
        browser = config['browser']
        name = browser.get('driver', 'Chrome')
        if not isinstance(name, str) or name.lower() not in ('chrome', 'edge'):
            raise ValueError('瀏覽器 driver 只支援 Chrome 或 Edge。')
        browser['driver'] = name.capitalize()
        for key in ('chrome_binary', 'chromedriver_path'):
            value = browser.get(key, '')
            if not isinstance(value, str):
                raise ValueError('瀏覽器及驅動路徑必須是文字。')
            if value:
                path = Path(value).expanduser()
                path = path if path.is_absolute() else base_dir / path
                if not path.is_file():
                    raise ValueError('找不到指定瀏覽器或驅動；請檢查設定路徑，或留空自動偵測。')
                browser[key] = str(path.resolve())
        evaluation = config['evaluation']
        if not isinstance(evaluation['submit'], bool):
            raise ValueError('submit 必須為 true 或 false。')
        for key, floor in (('maxCourses', 0), ('dryRunLimit', 1)):
            value = evaluation.get(key)
            if key == 'maxCourses' and value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < floor:
                raise ValueError('課程上限須為非負整數；預覽數量至少為 1。')
        download = config['download']
        for key in ('headless', 'close_browser_on_finish'):
            if not isinstance(download.get(key, False), bool):
                raise ValueError('瀏覽器開關須為 true 或 false。')
        if not values[0] and download.get('headless'):
            raise ValueError('手動登入時不能隱藏瀏覽器；請設 headless=false。')
        directory = Path(download.get('download_dir') or 'downloads')
        download['download_dir'] = str(directory if directory.is_absolute() else base_dir / directory)
        if not isinstance(config['portal']['webvpn_login_url'], str) or not config['portal']['webvpn_login_url'].startswith('https://'):
            raise ValueError('WebVPN 登入網址須為 HTTPS。')
    except (TypeError, KeyError, AttributeError):
        raise ValueError('設定結構錯誤；請參考設定範例。') from None
    return config


def load_public_config(defaults: dict, config_path: Path | None = None,
                       base_dir: Path | None = None) -> dict:
    root = Path(base_dir or app_directory()).resolve()
    config = copy.deepcopy(defaults)
    explicit = config_path is not None
    if explicit:
        path = Path(config_path)
        path = path if path.is_absolute() else root / path
        if not path.is_file():
            raise FileNotFoundError('找不到指定設定檔；請檢查 --config。')
    elif (root/'config.ini').is_file():
        path = root/'config.ini'
    else:
        legacy = root/'config/logincopy.config.json'
        if legacy.is_file() or (root/'.env').is_file():
            path = legacy
        else:
            template = Path(__file__).with_name('config.example.ini')
            (root/'config.ini').write_bytes(template.read_bytes())
            raise FirstRunConfig('已建立 config.ini。請填寫設定後重新啟動；帳密留空可手動登入。')
    if path.suffix.lower() == '.ini':
        _ini(path, config)
    else:
        if path.is_file():
            try:
                extra = json.loads(path.read_text(encoding='utf-8-sig'))
                if not isinstance(extra, dict):
                    raise ValueError()
                _merge(config, extra)
            except (ValueError, UnicodeError):
                raise ValueError('JSON 設定格式錯誤。') from None
        if not explicit:
            env = _dotenv(root/'.env')
            for dest, key in (('webvpn_username', 'USER_ID'), ('webvpn_password', 'USER_PASSWORD')):
                config['credentials'][dest] = config['credentials'].get(dest) or env.get(key, '')
            config['portal']['webvpn_login_url'] = config['portal'].get('webvpn_login_url') or env.get('LOGIN_URL', '')
    return validate_config(config, root)
