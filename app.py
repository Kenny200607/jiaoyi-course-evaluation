"""Shared console entry point for source and the Windows portable application."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from release_config import FirstRunConfig, app_directory, load_public_config, validate_config
from privacy import RedactingStream, redact

VERSION = '0.1.1'


def main(argv=None, base_dir=None) -> int:
    import logincopy
    parser = argparse.ArgumentParser(description='交醫課程評價工具：預覽為預設模式，正式提交前須確認。')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--config', type=Path, help='INI 或相容的 JSON 設定檔')
    parser.add_argument('--mode', choices=['schedule', 'evaluation'], default='evaluation')
    parser.add_argument('--submit', action='store_true', help='啟用正式提交（仍須本次確認）')
    parser.add_argument('--dry-run', action='store_true', help='強制預覽，即使設定已啟用正式提交')
    parser.add_argument('--max-courses', type=int)
    parser.add_argument('--dry-run-limit', type=int)
    parser.add_argument('--check', action='store_true', help='檢查設定，不啟動瀏覽器')
    parser.add_argument('--diagnose', action='store_true', help='檢查依賴及 OCR 模型，不登入學校')
    parser.add_argument('--check-browser', action='store_true', help='開啟本地測試頁檢查瀏覽器，不登入學校')
    parser.add_argument('--pause', action='store_true', help='結束時保留提示，適合雙擊啟動')
    args = parser.parse_args(argv)
    root = Path(base_dir or app_directory()).resolve()
    logger = None
    original = sys.stdout, sys.stderr
    secrets = ()
    try:
        config = load_public_config(logincopy.DEFAULT_CONFIG, args.config, root)
        secrets = tuple(config['credentials'].values())
        if args.submit and args.dry_run:
            raise ValueError('不能同時使用 --submit 和 --dry-run。')
        if args.submit:
            config['evaluation']['submit'] = True
        if args.dry_run:
            config['evaluation']['submit'] = False
        if args.max_courses is not None:
            config['evaluation']['maxCourses'] = args.max_courses
        if args.dry_run_limit is not None:
            config['evaluation']['dryRunLimit'] = args.dry_run_limit
        validate_config(config, root)
        if args.check:
            print(json.dumps({
                'version': VERSION,
                'login': 'automatic' if config['credentials']['webvpn_username'] else 'manual',
                'browser': config['browser']['driver'],
                'evaluation_submit': config['evaluation']['submit'],
                'evaluation_max_courses': config['evaluation']['maxCourses'],
                'dry_run_limit': config['evaluation']['dryRunLimit'],
            }, ensure_ascii=False))
            return 0
        (root/'logs').mkdir(exist_ok=True)
        logger = logincopy.configure_output(root/'logs/evaluation.log')
        sys.stdout = RedactingStream(sys.stdout, secrets)
        sys.stderr = RedactingStream(sys.stderr, secrets)
        if args.diagnose:
            import selenium
            from selenium.webdriver.common.selenium_manager import SeleniumManager
            print('Selenium:', selenium.__version__)
            print('Selenium Manager:', 'available' if SeleniumManager._get_binary().is_file() else 'missing')
            try:
                import ddddocr
            except ImportError:
                print('OCR: optional dependency not installed; manual verification remains available.')
            else:
                ddddocr.DdddOcr(show_ad=False)
                print('OCR: model loaded successfully')
            session = logincopy.LoginCopySession(config)
            print('Browser:', config['browser']['driver'], 'found' if session._resolve_chrome_binary() else 'not found')
            return 0
        if args.check_browser:
            import copy
            smoke = copy.deepcopy(config)
            smoke['download'].update(headless=True, close_browser_on_finish=True)
            with logincopy.LoginCopySession(smoke) as session:
                session.driver.get('data:text/html,<title>Local browser check</title><p>OK</p>')
                if session.driver.title != 'Local browser check':
                    raise RuntimeError('本地瀏覽器測試頁未正確載入。')
                print('Local browser check: PASS')
            return 0
        print('模式：', '正式提交' if config['evaluation']['submit'] else '預覽（不提交）')
        print('評分方式：每列最後一個單選項；請先預覽確認頁面選項。')
        print('課程上限：', config['evaluation']['maxCourses'] or '全部有效未完成記錄')
        if args.mode == 'evaluation' and config['evaluation']['submit']:
            try:
                approved = input('本次要正式提交嗎？輸入 SUBMIT 確認，其餘輸入取消：').strip() == 'SUBMIT'
            except EOFError:
                approved = False
            if not approved:
                print('已取消，未啟動評價。')
                return 0
        if args.mode == 'evaluation':
            logincopy.run_evaluation_flow(config)
        else:
            logincopy.run_login_flow(config)
        return 0
    except FirstRunConfig as exc:
        print(str(exc))
        return 0
    except KeyboardInterrupt:
        print('已停止。', file=sys.stderr)
        return 130
    except Exception as exc:
        print('錯誤：' + redact(str(exc), secrets), file=sys.stderr)
        return 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        if logger:
            logger.close()
        sys.stdout, sys.stderr = original
        if args.pause:
            try:
                input('按 Enter 結束…')
            except EOFError:
                pass


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    launch_args = sys.argv[1:]
    if getattr(sys, 'frozen', False) and not launch_args:
        launch_args = ['--pause']
    raise SystemExit(main(launch_args))
