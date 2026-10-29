"""Shared console entry point for source and the Windows portable application."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from release_config import FirstRunConfig, app_directory, load_public_config, validate_config
from privacy import RedactingStream, redact

VERSION = '0.1.4'
APP_NAME = '交医课程评价工具'


def main(argv=None, base_dir=None) -> int:
    import logincopy
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(APP_NAME)
    parser = argparse.ArgumentParser(description='交医课程评价工具：预览为默认模式，正式提交前须确认。')
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('--config', type=Path, help='INI 或兼容的 JSON 设置档')
    parser.add_argument('--mode', choices=['schedule', 'evaluation'], default='evaluation')
    parser.add_argument('--submit', action='store_true', help='启用正式提交（仍须本次确认）')
    parser.add_argument('--dry-run', action='store_true', help='强制预览，即使设置已启用正式提交')
    parser.add_argument('--max-courses', type=int)
    parser.add_argument('--dry-run-limit', type=int)
    parser.add_argument('--rating-level', help='评分等级：highest（默认最高级）或 1、2、3 等正整数')
    parser.add_argument('--check', action='store_true', help='检查设置，不启动浏览器')
    parser.add_argument('--diagnose', action='store_true', help='检查依赖及 OCR 模型，不登录学校')
    parser.add_argument('--check-browser', action='store_true', help='开启本地测试页检查浏览器，不登录学校')
    parser.add_argument('--pause', action='store_true', help='结束时保留提示，适合双击启动')
    args = parser.parse_args(argv)
    root = Path(base_dir or app_directory()).resolve()
    logger = None
    original = sys.stdout, sys.stderr
    secrets = ()
    try:
        config = load_public_config(logincopy.DEFAULT_CONFIG, args.config, root)
        secrets = tuple(config['credentials'].values())
        if args.submit and args.dry_run:
            raise ValueError('不能同时使用 --submit 和 --dry-run。')
        if args.submit:
            config['evaluation']['submit'] = True
        if args.dry_run:
            config['evaluation']['submit'] = False
        if args.max_courses is not None:
            config['evaluation']['maxCourses'] = args.max_courses
        if args.dry_run_limit is not None:
            config['evaluation']['dryRunLimit'] = args.dry_run_limit
        if args.rating_level is not None:
            config['evaluation']['ratingLevel'] = args.rating_level
            config['evaluation']['ratingStrategy'] = 'last-radio-per-row'
        validate_config(config, root)
        if args.check:
            print(json.dumps({
                'version': VERSION,
                'login': 'automatic' if config['credentials']['webvpn_username'] else 'manual',
                'browser': config['browser']['driver'],
                'evaluation_submit': config['evaluation']['submit'],
                'evaluation_max_courses': config['evaluation']['maxCourses'],
                'dry_run_limit': config['evaluation']['dryRunLimit'],
                'rating_level': config['evaluation']['ratingLevel'],
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
                    raise RuntimeError('本地浏览器测试页未正确载入。')
                print('Local browser check: PASS')
            return 0
        print(APP_NAME)
        print('模式：', '正式提交' if config['evaluation']['submit'] else '预览（不提交）')
        level = config['evaluation']['ratingLevel']
        print('评分等级：', '最高级（每题最后一项）' if level == 'highest' else f'第 {level} 级（每题第 {level} 项）')
        print('请先预览确认页面选项从低到高排列；指定等级不存在时会停止。')
        print('课程上限：', config['evaluation']['maxCourses'] or '全部有效未完成记录')
        if args.mode == 'evaluation' and config['evaluation']['submit']:
            try:
                approved = input('本次要正式提交吗？输入 SUBMIT 确认，其余输入取消：').strip() == 'SUBMIT'
            except EOFError:
                approved = False
            if not approved:
                print('已取消，未启动评价。')
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
        print('错误：' + redact(str(exc), secrets), file=sys.stderr)
        return 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        if logger:
            logger.close()
        sys.stdout, sys.stderr = original
        if args.pause:
            try:
                input('按 Enter 结束…')
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
