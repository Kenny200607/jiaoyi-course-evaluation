"""Reusable WebVPN login flow extracted from AutoCourseDownload.

This file packages the browser startup and login portion of the project into a
single standalone helper that can be copied into another Python program.

Flow:
1. Start Chrome through Selenium.
2. Open the WebVPN login page.
3. Fill username/password.
4. If the login verification field is present, ask the user to type it once.
5. Click the login button.
6. Open the teaching system.
7. Open the schedule page.

Minimal config shape:
{
  "credentials": {
    "webvpn_username": "...",
    "webvpn_password": "..."
  },
  "browser": {
    "chrome_binary": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "chromedriver_path": "C:\\path\\to\\chromedriver.exe"
  },
  "portal": {
    "webvpn_login_url": "...",
    "teaching_system_text": "teaching-system-label",
    "schedule_text_keyword": "schedule-label",
    "selectors": {
      "username": "username",
      "password": "password",
      "captcha_image_xpath": "...",
      "captcha_input_xpath": "...",
      "login_button_xpath": "..."
    }
  },
  "download": {
    "download_dir": "downloads",
    "headless": false,
    "close_browser_on_finish": false
  }
}
"""

from __future__ import annotations

import copy
import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from browser_support import browser_name, find_browser, file_version, versions_match


def require_module(module_name: str, install_hint: str):
    try:
        return __import__(module_name)
    except ImportError as exc:
        raise RuntimeError(f"Missing dependency: {module_name}. Install it with: {install_hint}") from exc


class Tee:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


class LogSession:
    def __init__(self, log_file, stdout, stderr) -> None:
        self.log_file = log_file
        self.stdout = stdout
        self.stderr = stderr

    def close(self) -> None:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            sys.stdout = self.stdout
            sys.stderr = self.stderr
            self.log_file.close()


def configure_output(log_path: Path | None = None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if log_path is None:
        return None

    log_file = log_path.open("w", encoding="utf-8", buffering=1)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)
    print(f"Log file: {log_path.resolve()}")
    return LogSession(log_file, original_stdout, original_stderr)


def cleanup_screenshots() -> None:
    screenshot_root = Path("screenshots")
    logincopy_screenshots = screenshot_root / "logincopy"

    if not logincopy_screenshots.exists():
        return

    try:
        shutil.rmtree(logincopy_screenshots)
        try:
            screenshot_root.rmdir()
        except OSError:
            pass
        print("Cleaned screenshots.")
    except Exception as exc:
        print(f"Could not clean screenshots: {exc}")







DEFAULT_CONFIG = {
    "credentials": {
        "webvpn_username": "",
        "webvpn_password": "",
    },
    "browser": {
        "chrome_binary": "",
        "chromedriver_path": "",
    },
    "portal": {
        "webvpn_login_url": "https://webvpn2.shsmu.edu.cn/",
        "teaching_system_text": "教务系统",
        "schedule_text_keyword": "课表",
        "course_evaluation_text": "课程评价",
        "course_evaluation_url": (
            "https://webvpn2.shsmu.edu.cn/https/"
            "77726476706e69737468656265737421fae05288327e7b586d059ce29d51367b9aac/"
            "UMC_Evaluation/StudentCourseRecord"
        ),
        "selectors": {
            "username": "username",
            "password": "password",
            "username_xpath": (
                "//input[not(@type='hidden') and ("
                "@id='username' or @name='username' or @id='userName' or @name='userName' or "
                "contains(@placeholder, '用户名') or contains(@placeholder, '账号') or "
                "contains(@placeholder, '帳號') or contains(@placeholder, '学号') or "
                "contains(@placeholder, '學號') or contains(@placeholder, '邮箱') or "
                "@autocomplete='username')]"
            ),
            "password_xpath": (
                "//input[not(@type='hidden') and ("
                "@type='password' or @id='password' or @name='password' or "
                "contains(@placeholder, '密码') or contains(@placeholder, '密碼') or "
                "@autocomplete='current-password')]"
            ),
            "captcha_image_xpath": (
                "//img[@id='captcha-img'] | //img[contains(@src, 'captcha')] | "
                "//img[contains(@onclick, 'captcha')]"
            ),
            "captcha_input_xpath": (
                "//input[@id='captcha'] | //input[@name='captcha'] | "
                "//input[contains(@placeholder, '验证码')] | //input[contains(@placeholder, '驗證碼')]"
            ),
            "login_button_xpath": (
                "//button[contains(., '登录')] | //button[contains(., '登入')] | "
                "//button[contains(., '登錄')] | //input[contains(@value, '登录')] | "
                "//input[contains(@value, '登入')] | //input[contains(@class, 'login_box_landing')] | "
                "//a[contains(., '登录')] | //a[contains(., '登入')]"
            ),
        },
    },
    "download": {
        "download_dir": "downloads",
        "headless": False,
        "close_browser_on_finish": False,
    },
    "evaluation": {
        "submit": False,
        "maxCourses": None,
        "dryRunLimit": 1,
        "ratingStrategy": "last-radio-per-row",
        "ratingValue": "5",
        "comment": "",
        "incompleteStatusLabels": ["未完成", "待评价", "待評價", "Incomplete"],
        "courseEntryLabels": ["查看", "评价", "評價", "评教", "評教", "Reply", "Evaluate"],
        "ratingRadioSelectors": [
            "input[type='radio'][value='{ratingValue}']",
            "input[type='radio'][aria-label*='{ratingValue}']",
        ],
        "ratingSelectSelectors": ["select"],
        "commentSelectors": [
            "textarea",
            "input[type='text'][name*='comment']",
            "input[type='text'][placeholder*='意见']",
            "input[type='text'][placeholder*='意見']",
            "input[type='text'][placeholder*='建议']",
            "input[type='text'][placeholder*='建議']",
        ],
        "submitLabels": ["提交", "保存", "Submit", "Save"],
        "backLabels": ["返回", "上一页", "上一頁", "Back"],
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def parse_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    pieces = []
    for index, part in enumerate(parts):
        if part:
            pieces.append(f"'{part}'")
        if index != len(parts) - 1:
            pieces.append('"\'"')
    return "concat(" + ", ".join(pieces) + ")"


def unique_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def is_null_evaluation_record(record: dict) -> bool:
    """Return whether a course row has no usable course data to evaluate."""
    if not isinstance(record, dict):
        return True

    for field_name in ("CourseType", "CoursesContent"):
        value = record.get(field_name)
        if value is None:
            return True
        if isinstance(value, str) and value.strip().casefold() in {
            "null",
            "none",
            "undefined",
        }:
            return True
    return False


def build_action_text_xpath(labels: list[str]) -> str:
    clauses = []
    for label in unique_strings(labels):
        literal = xpath_literal(label)
        clauses.append(f"contains(normalize-space(.), {literal}) or contains(@value, {literal})")
    if not clauses:
        clauses.append("false()")
    return (
        "//*[self::a or self::button or @role='button' or self::input]"
        f"[({' or '.join(clauses)})]"
    )


def selectors_for_rating(selectors: list[str], rating_value: str) -> list[str]:
    return [selector.replace("{ratingValue}", rating_value) for selector in selectors]


def last_radio_per_row_script() -> str:
    return r"""
        const rows = Array.from(document.querySelectorAll('tr'));

        function isUsable(element) {
            if (!element || element.disabled) return false;
            const style = window.getComputedStyle(element);
            return style.display !== 'none' && style.visibility !== 'hidden';
        }

        function chooseRadio(target) {
            if (!target || !isUsable(target)) return false;

            target.scrollIntoView({ block: 'center', inline: 'center' });

            const label = target.closest('label');
            const wrapper = target.closest(
                '[class*="iradio"], [class*="iCheck"], [class*="icheck"], [class*="radio"]'
            ) || target.parentElement;
            const helper = wrapper
                ? wrapper.querySelector('ins, .iCheck-helper, [class*="iradio"], [class*="iCheck"], [class*="icheck"]')
                : null;
            const clickable = label || helper || wrapper || target;

            if (window.jQuery && window.jQuery.fn && window.jQuery.fn.iCheck) {
                window.jQuery(target).iCheck('check');
            }

            if (!target.checked) {
                try {
                    clickable.click();
                } catch (error) {
                    target.click();
                }
            }

            target.checked = true;
            target.setAttribute('checked', 'checked');

            if (wrapper && wrapper.classList && /radio|iradio|icheck/i.test(String(wrapper.className))) {
                wrapper.classList.add('checked');
            }

            target.dispatchEvent(new Event('input', { bubbles: true }));
            target.dispatchEvent(new Event('change', { bubbles: true }));
            return target.checked;
        }

        let checked = 0;

        for (const row of rows) {
            const rowStyle = window.getComputedStyle(row);
            if (rowStyle.display === 'none' || rowStyle.visibility === 'hidden') continue;

            const cellsWithRadios = Array.from(row.querySelectorAll('td, th')).filter((cell) => {
                return cell.querySelector('input[type="radio"]');
            });
            if (!cellsWithRadios.length) continue;

            const lastCell = cellsWithRadios[cellsWithRadios.length - 1];
            const radios = Array.from(lastCell.querySelectorAll('input[type="radio"]'));
            const target = radios[radios.length - 1];
            if (chooseRadio(target)) checked += 1;
        }

        if (checked === 0) {
            const groups = new Map();
            document.querySelectorAll('input[type="radio"]').forEach((radio) => {
                if (!radio.name) return;
                if (!groups.has(radio.name)) groups.set(radio.name, []);
                groups.get(radio.name).push(radio);
            });

            for (const group of groups.values()) {
                const target = group[group.length - 1];
                if (chooseRadio(target)) checked += 1;
            }
        }

        return checked;
    """


def radio_row_status_script() -> str:
    return r"""
        let total = 0;
        let checked = 0;
        let missing = 0;

        for (const row of Array.from(document.querySelectorAll('tr'))) {
            const rowStyle = window.getComputedStyle(row);
            if (rowStyle.display === 'none' || rowStyle.visibility === 'hidden') continue;

            const radios = Array.from(row.querySelectorAll('input[type="radio"]'));
            if (!radios.length) continue;

            total += 1;
            if (row.querySelector('input[type="radio"]:checked')) {
                checked += 1;
            } else {
                missing += 1;
            }
        }

        return { total, checked, missing };
    """


def rewrite_webvpn_app_url(current_url: str, list_url: str) -> str:
    marker = "/UMC_Evaluation/"
    if marker not in current_url or marker not in list_url:
        return current_url

    current_prefix, current_suffix = current_url.split(marker, 1)
    list_prefix, _ = list_url.split(marker, 1)
    if current_prefix == list_prefix:
        return current_url
    if "/https/" in current_prefix:
        return current_url
    return f"{list_prefix}{marker}{current_suffix}"


def load_config(config_path: Path | None = None) -> dict:
    from release_config import load_public_config
    return load_public_config(DEFAULT_CONFIG, config_path)


class LoginCopySession:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.driver = None
        self.wait = None
        self._selenium = None
        self._browser_profile_dir: Path | None = None
        self._chrome_process = None
        self._driver_service = None
        self._evaluation_page = 1
    def _auto_solve_captcha(self) -> bool:
        """OCR 驗證碼自動識別與填充"""
        # 確保頂部有 import re 和 import ddddocr (如果有的話)
        try:
            import ddddocr
            import re
            ocr = ddddocr.DdddOcr(show_ad=False)
        except Exception:
            print("OCR 無法啟動，請在瀏覽器手動完成驗證。")
            return False

        s = self._selenium
        By = s["By"]
        EC = s["EC"]
        
        try:
            # 1. 截取圖片
            try:
                xpath_img = self.selectors.get("captcha_image_xpath")
                captcha_img = self.wait.until(EC.visibility_of_element_located((By.XPATH, xpath_img)))
                img_data = captcha_img.screenshot_as_png
            except Exception:
                all_imgs = self.driver.find_elements(By.TAG_NAME, "img")
                visible_imgs = [i for i in all_imgs if i.is_displayed() and i.size['width'] > 20]
                if not visible_imgs: return False
                img_data = visible_imgs[0].screenshot_as_png

            # 2. 辨識與計算
            res_text = ocr.classification(img_data)
            nums = re.findall(r'\d+', res_text)
            
            if len(nums) >= 2:
                ans = int(nums[0]) + int(nums[1])
            else:
                ans = res_text

            # 3. 填入
            xpath_input = self.selectors.get("captcha_input_xpath")
            captcha_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath_input)))
            captcha_input.clear()
            captcha_input.send_keys(str(ans))
            return True
        except Exception as e:
            print(f"   ❌ 自動辨識失敗: {e}")
            return False
    
    def __enter__(self) -> "LoginCopySession":
        try:
            return self._start_browser()
        except BaseException:
            self._cleanup_browser(force_close=True)
            raise

    def _start_browser(self) -> "LoginCopySession":
        self._selenium = self._load_selenium()
        webdriver = self._selenium["webdriver"]
        Options = self._selenium["Options"]
        Service = self._selenium["Service"]
        WebDriverWait = self._selenium["WebDriverWait"]

        download_dir = Path(self.config["download"]["download_dir"])
        download_dir.mkdir(parents=True, exist_ok=True)

        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-debugging-port=0")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-component-update")
        chrome_options.add_argument("--disable-crash-reporter")
        chrome_options.add_argument("--disable-breakpad")
        chrome_options.add_argument("--disable-features=Crashpad")
        chrome_options.add_argument("--noerrdialogs")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])
        chrome_options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": str(download_dir),
                "download.prompt_for_download": False,
                "plugins.always_open_pdf_externally": True,
            },
        )
        chrome_options.add_argument(f"--user-data-dir={self._prepare_browser_profile_dir()}")
        chrome_options.add_argument("--profile-directory=Default")
        if self.config.get("download", {}).get("headless", False):
            chrome_options.add_argument("--headless=new")

        chrome_binary = self._resolve_chrome_binary()
        if chrome_binary:
            chrome_options.binary_location = chrome_binary

        chromedriver_path = self._resolve_chromedriver_path()
        if not chromedriver_path:
            raise RuntimeError("Could not find a local chromedriver.exe.")

        try:
            self._driver_service = Service(executable_path=str(chromedriver_path))
            self.driver = (webdriver.Edge if browser_name(self.config.get("browser", {})) == "Edge" else webdriver.Chrome)(
                service=self._driver_service,
                options=chrome_options,
            )
        except Exception:
            self._stop_driver_service()
            if not chrome_binary:
                raise
            self.driver = self._attach_to_manually_started_chrome(
                webdriver=webdriver,
                Options=Options,
                Service=Service,
                chromedriver_path=chromedriver_path,
                chrome_binary=chrome_binary,
                download_dir=download_dir,
            )

        self.wait = WebDriverWait(self.driver, 20)
        print(f"{browser_name(self.config.get('browser', {}))} started. Driver: {chromedriver_path}")
        return self

    def _stop_driver_service(self) -> None:
        """Stop chromedriver without retrying a stale Windows process handle."""
        service = getattr(self.driver, "service", None) or getattr(self, "_driver_service", None)
        process = getattr(service, "process", None)
        if process is None:
            return

        try:
            try:
                running = process.poll() is None
            except (OSError, ValueError):
                running = True

            if running:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                        process.wait(timeout=5)
                    except OSError:
                        pass
                except (OSError, ValueError):
                    pass
        finally:
            for stream_name in ("stdin", "stdout", "stderr"):
                stream = getattr(process, stream_name, None)
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
            service.process = None

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._cleanup_browser(force_close=exc_type is not None)

    def _cleanup_browser(self, force_close: bool = False) -> None:
        close_browser = force_close or self.config.get("download", {}).get("close_browser_on_finish", False)
        if self.driver and close_browser:
            try:
                self.driver.quit()
            except Exception as error:
                print(f"Browser shutdown notice: {error}")
        self._stop_driver_service()
        if close_browser and self._chrome_process:
            try:
                if self._chrome_process.poll() is None:
                    self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._chrome_process.kill()
                self._chrome_process.wait(timeout=5)
            except OSError:
                pass
        if self._browser_profile_dir and (close_browser or not self.driver):
            shutil.rmtree(self._browser_profile_dir, ignore_errors=True)

    @property
    def selectors(self) -> dict:
        return self.config.get("portal", {}).get("selectors", {})

    def _selector_to_locator(self, value: str, default_id: str):
        By = self._selenium["By"]
        selector = (value or default_id).strip()
        if selector.startswith("//") or selector.startswith("("):
            return By.XPATH, selector
        if (
            selector.startswith("#")
            or selector.startswith(".")
            or selector.startswith("[")
            or selector.startswith("input")
            or selector.startswith("button")
        ):
            return By.CSS_SELECTOR, selector
        return By.ID, selector.lstrip("#")

    def _login_field_locators(self, field_name: str):
        By = self._selenium["By"]
        if field_name == "username":
            configured = self.selectors.get("username", "username")
            fallback_xpath = self.selectors.get(
                "username_xpath",
                "//input[not(@type='hidden') and ("
                "@id='username' or @name='username' or @id='userName' or @name='userName' or "
                "contains(@placeholder, '用户名') or contains(@placeholder, '账号') or "
                "contains(@placeholder, '帳號') or contains(@placeholder, '学号') or "
                "contains(@placeholder, '學號') or contains(@placeholder, '邮箱') or "
                "@autocomplete='username')]",
            )
            modern_xpath = (
                "//input[not(@type='hidden') and ("
                "@id='username' or @name='username' or @id='userName' or @name='userName' or "
                "@autocomplete='username' or contains(@placeholder, '\u8d26\u53f7') or "
                "contains(@placeholder, '\u7528\u6237') or contains(@placeholder, '\u5b66\u53f7') or "
                "contains(@placeholder, '\u5de5\u53f7') or contains(@placeholder, '\u624b\u673a') or "
                "contains(@placeholder, 'Email'))]"
            )
            return [
                self._selector_to_locator(configured, "username"),
                (By.XPATH, fallback_xpath),
                (By.XPATH, modern_xpath),
            ]

        configured = self.selectors.get("password", "password")
        fallback_xpath = self.selectors.get(
            "password_xpath",
            "//input[not(@type='hidden') and ("
            "@type='password' or @id='password' or @name='password' or "
            "contains(@placeholder, '密码') or contains(@placeholder, '密碼') or "
            "@autocomplete='current-password')]",
        )
        modern_xpath = (
            "//input[not(@type='hidden') and ("
            "@type='password' or @id='password' or @name='password' or "
            "@autocomplete='current-password' or contains(@placeholder, '\u5bc6\u7801'))]"
        )
        return [
            self._selector_to_locator(configured, "password"),
            (By.XPATH, fallback_xpath),
            (By.XPATH, modern_xpath),
        ]

    def _find_visible_element_in_current_context(self, locators):
        for by, value in locators:
            try:
                for element in self.driver.find_elements(by, value):
                    if element.is_displayed() and element.is_enabled():
                        return element
            except Exception:
                continue
        return None

    def _wait_for_login_field(self, field_name: str, timeout_seconds: int = 20):
        deadline = time.time() + timeout_seconds
        locators = self._login_field_locators(field_name)
        By = self._selenium["By"]

        while time.time() < deadline:
            self.driver.switch_to.default_content()
            element = self._find_visible_element_in_current_context(locators)
            if element:
                return element

            for iframe in self.driver.find_elements(By.TAG_NAME, "iframe"):
                self.driver.switch_to.default_content()
                try:
                    self.driver.switch_to.frame(iframe)
                except Exception:
                    continue
                element = self._find_visible_element_in_current_context(locators)
                if element:
                    return element

            time.sleep(0.5)

        raise RuntimeError(f"Could not find visible login field: {field_name}")

    def _print_page_state(self, step_name: str) -> None:
        if not self.driver:
            return
        try:
            title = self.driver.title
        except Exception:
            title = "(no title)"
        try:
            url = self.driver.current_url
        except Exception:
            url = "(no url)"
        print(f"Step [{step_name}]")
        print(f"Page title: {title or '(no title)'}")
        print(f"Page url: {url}")

    def _load_selenium(self) -> dict:
        require_module("selenium", "python -m pip install selenium")
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException
        if browser_name(self.config.get("browser", {})) == "Edge":
            from selenium.webdriver.edge.options import Options
            from selenium.webdriver.edge.service import Service
        else:
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        return {
            "webdriver": webdriver,
            "Options": Options,
            "Service": Service,
            "By": By,
            "EC": EC,
            "Select": Select,
            "TimeoutException": TimeoutException,
            "WebDriverWait": WebDriverWait,
        }

    def _resolve_chrome_binary(self) -> str | None:
        return find_browser(self.config.get("browser", {}))

    def _resolve_chromedriver_path(self) -> Path | None:
        name = browser_name(self.config.get("browser", {}))
        driver_name = "msedgedriver" if name == "Edge" else "chromedriver"
        chrome_major = self._chrome_major_version()
        if not chrome_major:
            raise RuntimeError(f"Could not determine {name} version. Check browser exe_path.")
        browser_version = (file_version(self._resolve_chrome_binary()) or "") if name == "Edge" else chrome_major

        def matching(path):
            version = self._driver_version(Path(path))
            return bool(version and versions_match(name, browser_version, version))

        candidates: list[Path] = []
        configured = self.config.get("browser", {}).get("chromedriver_path")
        which_path = shutil.which(driver_name)
        for candidate in (configured, which_path):
            if candidate and Path(candidate).is_file():
                if matching(candidate):
                    return Path(candidate)
                print(f"Ignoring driver that does not match {name} {chrome_major}.")

        cache_root = Path.home() / ".cache" / "selenium" / driver_name / "win64"
        if cache_root.exists():
            candidates = list(cache_root.glob(f"*/{driver_name}.exe"))
        candidates = [path for path in candidates if path.parent.name.split('.')[0] == chrome_major]
        for candidate in sorted(candidates, key=lambda path: tuple(
            int(part) for part in re.findall(r'\d+', path.parent.name)
        ), reverse=True):
            if matching(candidate):
                return candidate

        candidate = self._managed_chromedriver_path()
        if candidate.is_file() and matching(candidate):
            return candidate
        raise RuntimeError(f"Could not obtain a driver matching {name} {chrome_major}.")

    def _chromedriver_major_version(self, path: Path) -> str | None:
        version = self._driver_version(path)
        return version.split('.')[0] if version else None

    def _driver_version(self, path: Path) -> str | None:
        try:
            result = subprocess.run(
                [str(path), "--version"], capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            match = re.search(r"(?:ChromeDriver|MSEdgeDriver|Microsoft Edge WebDriver) (\d+(?:\.\d+)+)", result.stdout or "")
            return match.group(1) if result.returncode == 0 and match else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _managed_chromedriver_path(self) -> Path:
        from selenium.webdriver.common.selenium_manager import SeleniumManager

        name = browser_name(self.config.get("browser", {})).lower()
        args = ["--browser", name, "--skip-driver-in-path", "--avoid-browser-download"]
        chrome_binary = self._resolve_chrome_binary()
        if chrome_binary:
            args.extend(["--browser-path", chrome_binary])
        print(f"Obtaining a matching {name} driver with Selenium Manager...")
        try:
            result = SeleniumManager().binary_paths(args)
            if result.get("driver_path"):
                return Path(result["driver_path"])
        except Exception as error:
            raise RuntimeError(f"Could not download a matching {name} driver: {error}") from error
        raise RuntimeError("Selenium Manager returned no driver path.")

    def _chrome_major_version(self) -> str | None:
        version_text = file_version(self._resolve_chrome_binary())
        return version_text.split('.')[0] if version_text else None

    def _browser_profile_base_dir(self) -> Path:
        configured = self.config.get("browser", {}).get("user_data_parent_dir")
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured))

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "LoginCopy" / "chrome-profiles")

        candidates.append(Path.cwd() / "tmp" / "chrome-profiles")

        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                probe = candidate / f".write-test-{uuid.uuid4().hex}"
                probe.mkdir()
                probe.rmdir()
                return candidate
            except OSError:
                continue

        raise RuntimeError("Could not create a Chrome profile folder for automation.")

    def _prepare_browser_profile_dir(self) -> str:
        if self._browser_profile_dir and self._browser_profile_dir.exists():
            return str(self._browser_profile_dir)

        base_dir = self._browser_profile_base_dir()
        self._browser_profile_dir = base_dir / f"chrome-profile-{uuid.uuid4().hex}"
        self._browser_profile_dir.mkdir(parents=True, exist_ok=True)
        (self._browser_profile_dir / "Default").mkdir(parents=True, exist_ok=True)
        return str(self._browser_profile_dir)

    def _free_tcp_port(self) -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    def _wait_for_debug_port(self, port: int, timeout_seconds: float = 15.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                    return True
            except OSError:
                time.sleep(0.25)
        return False

    def _attach_to_manually_started_chrome(
        self,
        webdriver,
        Options,
        Service,
        chromedriver_path: Path,
        chrome_binary: str,
        download_dir: Path,
    ):
        port = self._free_tcp_port()
        profile_dir = self._prepare_browser_profile_dir()
        args = [
            chrome_binary,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-component-update",
            "--disable-extensions",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--disable-features=Crashpad",
            "--noerrdialogs",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "about:blank",
        ]
        if self.config.get("download", {}).get("headless", False):
            args.insert(1, "--headless=new")

        self._chrome_process = subprocess.Popen(args)
        if not self._wait_for_debug_port(port):
            raise RuntimeError("Chrome could not be started for automation.")

        attach_options = Options()
        attach_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
        self._driver_service = Service(executable_path=str(chromedriver_path))
        driver = (webdriver.Edge if browser_name(self.config.get("browser", {})) == "Edge" else webdriver.Chrome)(
            service=self._driver_service,
            options=attach_options,
        )
        try:
            driver.execute_cdp_cmd(
                "Page.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": str(download_dir)},
            )
        except Exception:
            pass
        return driver

    def login_webvpn(self) -> None:
        d = self.driver
        s = self._selenium
        By = s["By"]
        EC = s["EC"]

        portal_config = self.config["portal"]
        credentials = self.config["credentials"]

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                print(f"Opening WebVPN login page... attempt {attempt}/3")
                d.get(portal_config["webvpn_login_url"])
                self._print_page_state("01-webvpn-login-opened")
                if self._is_webvpn_logged_in():
                    self._print_page_state("03-after-login-click")
                    return

                if not credentials.get("webvpn_username") and not credentials.get("webvpn_password"):
                    print("請在本次瀏覽器完成 WebVPN 登入；程式會等待登入完成。")
                    self._wait_until_webvpn_logged_in()
                    self._print_page_state("03-after-manual-login")
                    return

                print("Filling WebVPN username/password...")
                username_input = self._wait_for_login_field("username")
                username_input.clear()
                username_input.send_keys(credentials["webvpn_username"])

                password_input = self._wait_for_login_field("password")
                password_input.clear()
                password_input.send_keys(credentials["webvpn_password"])
                self._print_page_state("02-credentials-filled")

                manual_login_done = self._wait_for_browser_login_verification_if_present()
                if not manual_login_done:
                    print("Clicking login button...")
                    self._click_login_button()
                    self._wait_until_webvpn_logged_in(timeout_seconds=20)

                self._print_page_state("03-after-login-click")
                return
            except Exception as exc:
                last_error = exc
                print(f"Login attempt {attempt}/3 failed: {exc}")
                self._print_page_state(f"03-login-attempt-{attempt}-failed")
                if attempt < 3:
                    print("Restarting WebVPN login flow...")
                    continue
                raise

        if last_error:
            raise last_error

    def open_teaching_system(self) -> None:
        text = self.config["portal"].get("teaching_system_text", "\u6559\u52a1\u7cfb\u7edf")
        old_handles = set(self.driver.window_handles)
        xpath = (
            f"//div[contains(normalize-space(.), '{text}')]"
            f" | //a[contains(normalize-space(.), '{text}')]"
            " | //div[contains(normalize-space(.), '教务系统')]"
            " | //a[contains(normalize-space(.), '教务系统')]"
            " | //div[contains(normalize-space(.), '教務系統')]"
            " | //a[contains(normalize-space(.), '教務系統')]"
            " | //a[contains(., 'jwstu')]"
        )
        print("Opening teaching system...")
        self._click_xpath(xpath)
        self._switch_to_newest_window(old_handles)
        self.driver.switch_to.default_content()
        self._print_page_state("04-teaching-system-opened")

    def open_schedule(self) -> None:
        old_handles = set(self.driver.window_handles)
        keywords = [
            self.config["portal"].get("schedule_text_keyword", "\u8bfe\u8868"),
            "\u5b66\u751f\u8bfe\u8868",
            "\u6211\u7684\u8bfe\u8868",
            "\u8bfe\u8868",
            "課表",
            "\u6392\u8bfe",
        ]
        clicked = self.driver.execute_script(
            """
            const keywords = arguments[0];
            const tags = ["p", "span", "div", "a", "button", "li"];
            for (const tag of tags) {
              for (const el of document.getElementsByTagName(tag)) {
                const text = (el.innerText || el.textContent || "").trim();
                if (keywords.some((keyword) => text.includes(keyword))) {
                  el.scrollIntoView({block: "center"});
                  el.click();
                  return true;
                }
              }
            }
            return false;
            """,
            keywords,
        )
        if not clicked:
            self._print_page_state("05-schedule-entry-not-found")
            raise RuntimeError("Could not find the schedule entry.")

        print("Opening schedule page...")
        self._switch_to_newest_window(old_handles)
        self._close_duplicate_schedule_windows()
        time.sleep(2)
        self._print_page_state("05-schedule-opened")

    def open_webvpn_to_schedule(self) -> None:
        self.login_webvpn()
        self.open_teaching_system()
        self.open_schedule()

    def open_webvpn_to_course_evaluation(self) -> None:
        self.login_webvpn()
        self.open_teaching_system()
        self.open_course_evaluation()

    def open_course_evaluation(self) -> None:
        url = self.config["portal"].get("course_evaluation_url")
        if url:
            print("Opening course evaluation list directly...")
            self.driver.get(url)
            self._wait_for_bootstrap_table_data(".dg")
            self._print_page_state("05-course-evaluation-list-opened")
            return

        text = self.config["portal"].get("course_evaluation_text", "课程评价")
        print("Opening course evaluation list by menu text...")
        self._click_xpath(
            f"//*[self::a or self::button or self::span or self::div][contains(normalize-space(.), {xpath_literal(text)})]"
        )
        self._wait_for_bootstrap_table_data(".dg")
        self._print_page_state("05-course-evaluation-list-opened")

    def fill_all_course_evaluations(self) -> int:
        evaluation = self.config["evaluation"]
        limit = evaluation.get("maxCourses") if evaluation["submit"] else evaluation.get("dryRunLimit", 1)
        if limit is not None:
            limit = int(limit)
            if limit < 0:
                raise ValueError("Evaluation limits cannot be negative.")
            if evaluation["submit"] and limit == 0:
                limit = None
        completed = 0
        processed = 0
        seen_record_ids: set[str] = set()

        while limit is None or processed < limit:
            record = self._first_unfinished_student_course_record(seen_record_ids)
            if not record:
                print("No valid unfinished student course evaluation records remain.")
                break
            record_id = record.get("RecordID")

            print(
                "Opening evaluation record "
                f"{processed + 1}: {record.get('RecordToEvaluation', '')} "
                f"{record.get('CourseType', '')} {record.get('CoursesContent', '')}"
            )
            self._open_evaluation_record(record)
            self._print_page_state(f"06-evaluation-{processed + 1}-opened")
            self.fill_evaluation_form()
            self._print_page_state(f"07-evaluation-{processed + 1}-filled")

            submitted = self.submit_evaluation()

            if not evaluation["submit"]:
                try:
                    input("表單已填好，尚未提交。請在瀏覽器檢查後按 Enter 返回清單：")
                except EOFError:
                    print("沒有互動輸入；保留目前預覽頁，未提交。")
                    return completed

            self._return_to_course_evaluation_list()
            if submitted:
                if record_id and self._is_record_still_unfinished(record_id):
                    raise RuntimeError(
                        "Submit click returned, but the record is still marked unfinished."
                    )
                completed += 1

            if record_id:
                seen_record_ids.add(record_id)
            processed += 1

        if limit is not None and processed >= limit and evaluation["submit"]:
            if self._first_unfinished_student_course_record(seen_record_ids):
                print(f"Configured limit reached ({limit}); unfinished evaluation records remain.")

        print(f"Evaluation loop finished. Submitted forms: {completed}")
        return completed

    def fill_evaluation_form(self) -> None:
        evaluation = self.config["evaluation"]
        checked_count = 0

        if evaluation.get("ratingStrategy") == "last-radio-per-row":
            checked_count = self._check_last_radio_per_row()

        if checked_count == 0:
            for selector in selectors_for_rating(
                evaluation["ratingRadioSelectors"], evaluation["ratingValue"]
            ):
                radios = self.driver.find_elements(self._selenium["By"].CSS_SELECTOR, selector)
                for radio in radios:
                    if radio.is_displayed() and not radio.is_selected():
                        self.driver.execute_script("arguments[0].click();", radio)
                        checked_count += 1

        status = self._radio_row_status()
        if status["total"] and status["missing"]:
            raise RuntimeError(
                "Rating table is incomplete: "
                f"{status['checked']}/{status['total']} rows selected. "
                "Submit was not attempted."
            )

        comment = evaluation.get("comment", "")
        filled_comments = 0
        if comment.strip():
            filled_comments = self._fill_comment_fields(evaluation["commentSelectors"], comment)
        print(
            "Filled rating groups: "
            f"{checked_count}; verified rows: {status['checked']}/{status['total']}; "
            f"comment fields: {filled_comments}"
        )

    def submit_evaluation(self) -> bool:
        evaluation = self.config["evaluation"]
        if not evaluation["submit"]:
            print("Dry run mode: submit=false, so the form was filled but not submitted.")
            return False

        print("Submitting evaluation form...")
        self._print_submit_diagnostics()
        click_result = self._click_submit_control()
        public_result = {key: value for key, value in click_result.items() if key != "stateKey"}
        print(f"Submit click result: {json.dumps(public_result, ensure_ascii=False)}")
        if not click_result.get("clicked"):
            raise RuntimeError("Could not find a visible submit control on the evaluation form.")

        self._wait_for_submission(click_result.get("stateKey"))
        return True

    def _wait_for_submission(self, state_key: str | None = None) -> None:
        timeout_seconds = self.config["evaluation"].get("submitTimeoutSeconds", 60)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self._accept_possible_alert(timeout_seconds=0)
            state = self.driver.execute_script(
                """
                const key = arguments[0];
                if (key) {
                    try {
                        const stored = sessionStorage.getItem(key);
                        if (stored) return JSON.parse(stored);
                    } catch (_) {}
                }
                return window.__courseEvaluationSubmit || null;
                """,
                state_key,
            )
            if state and state.get("status") == "success":
                print("Submission confirmed by the server.")
                return
            if state and state.get("status") == "error":
                raise RuntimeError(f"Submission rejected: {state.get('message', 'Unknown server error')}")
            time.sleep(0.2)
        raise RuntimeError("Timed out waiting for submission confirmation; the form was not submitted again.")

    def _click_submit_control(self) -> dict:
        return self.driver.execute_script(
            r"""
            const recordId = new URL(location.href).searchParams.get('recordId') || location.pathname;
            const stateKey = 'course-evaluation-submit:' + recordId;
            const form = document.querySelector('form');
            if (!form || !window.jQuery || !jQuery.ajaxPrefilter) {
                return {clicked: false, reason: 'Evaluation AJAX form was not found'};
            }
            function appPath(url) {
                const path = new URL(url, location.href).pathname;
                const index = path.indexOf('/UMC_Evaluation/');
                return index < 0 ? path : path.slice(index);
            }
            window.__courseEvaluationSubmit = {
                status: 'pending', key: stateKey, action: appPath(form.action || location.href)
            };
            function remember(state) {
                window.__courseEvaluationSubmit = state;
                try { sessionStorage.setItem(stateKey, JSON.stringify(state)); } catch (_) {}
            }
            remember(window.__courseEvaluationSubmit);
            if (!window.__courseEvaluationObserverInstalled) {
                jQuery.ajaxPrefilter(function(options, originalOptions, request) {
                    const state = window.__courseEvaluationSubmit;
                    const method = String(options.type || 'GET').toUpperCase();
                    if (!state || state.status !== 'pending' || method !== 'POST'
                        || appPath(options.url) !== state.action) return;
                    const key = state.key;
                    function save(status, message) {
                        const result = {status: status, message: message || '', key: key};
                        window.__courseEvaluationSubmit = result;
                        try { sessionStorage.setItem(key, JSON.stringify(result)); } catch (_) {}
                    }
                    request.done(function(result) {
                        if (typeof result === 'string') {
                            try { result = JSON.parse(result); } catch (_) {}
                        }
                        save(result && result.status === 'success' ? 'success' : 'error',
                             result && result.message || 'Unexpected submission response');
                    });
                    request.fail(function(xhr, status, error) {
                        save('error', 'HTTP ' + xhr.status + ': ' + (error || status));
                    });
                });
                window.__courseEvaluationObserverInstalled = true;
            }
            const submitState = document.querySelector('#SubmitState');
            if (submitState) submitState.value = '1';

            function isVisible(element) {
                if (!element) return false;
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            }

            function labelOf(element) {
                return (element.innerText || element.textContent || element.value || element.title || '').trim();
            }

            const controls = Array.from(document.querySelectorAll(
                '#btnSure, #btnSubmit, #submit, button, input[type="button"], input[type="submit"], a, [onclick]'
            )).filter(isVisible);

            const preferred = controls.find((control) => control.id === 'btnSure')
                || controls.find((control) => /提交|保存|完成|submit|save|sure/i.test(labelOf(control)))
                || controls.find((control) => /submit|save|sure/i.test(control.id || control.name || control.className || ''));

            if (!preferred) {
                return {
                    clicked: false,
                    controls: controls.slice(0, 20).map((control) => ({
                        tag: control.tagName,
                        id: control.id || '',
                        className: String(control.className || ''),
                        label: labelOf(control)
                    }))
                };
            }

            preferred.scrollIntoView({ block: 'center', inline: 'center' });
            preferred.click();
            return {
                clicked: true,
                stateKey: stateKey,
                tag: preferred.tagName,
                id: preferred.id || '',
                className: String(preferred.className || ''),
                label: labelOf(preferred)
            };
            """
        )

    def _print_submit_diagnostics(self) -> None:
        diagnostics = self.driver.execute_script(
            r"""
            function isVisible(element) {
                if (!element) return false;
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && rect.width > 0
                    && rect.height > 0;
            }

            const invalid = Array.from(document.querySelectorAll('input, textarea, select'))
                .filter((field) => field.willValidate && !field.checkValidity())
                .map((field) => ({
                    tag: field.tagName,
                    type: field.type || '',
                    id: field.id || '',
                    name: field.name || '',
                    required: Boolean(field.required),
                    placeholder: field.getAttribute('placeholder') || '',
                    validationMessage: field.validationMessage || ''
                }));

            const controls = Array.from(document.querySelectorAll(
                '#btnSure, #btnSubmit, #submit, button, input[type="button"], input[type="submit"], a, [onclick]'
            ))
                .filter(isVisible)
                .slice(0, 20)
                .map((control) => ({
                    tag: control.tagName,
                    id: control.id || '',
                    name: control.name || '',
                    type: control.type || '',
                    className: String(control.className || ''),
                    label: (control.innerText || control.textContent || control.value || control.title || '').trim()
                }));

            return { invalid, controls };
            """
        )
        print(f"Submit diagnostics: {json.dumps(diagnostics, ensure_ascii=False)}")

    def _accept_possible_alert(self, timeout_seconds: float = 2.0) -> None:
        end_at = time.time() + timeout_seconds
        while True:
            try:
                alert = self.driver.switch_to.alert
                text = alert.text
                alert.accept()
                print(f"Accepted browser alert: {text}")
                return
            except Exception:
                if time.time() >= end_at:
                    return
                time.sleep(0.1)

    def _first_unfinished_student_course_record(self, seen_record_ids: set[str] | None = None) -> dict | None:
        seen_record_ids = seen_record_ids or set()
        visited_pages: set[int] = set()
        while True:
            records = self._wait_for_bootstrap_table_data(".dg")
            page = getattr(self, "_evaluation_page", 1)
            if page in visited_pages:
                return None
            visited_pages.add(page)
            for record in records:
                record_id = record.get("RecordID")
                if record.get("IsSubmit") or record_id in seen_record_ids:
                    continue
                if is_null_evaluation_record(record):
                    print("Skipping evaluation record with null course fields.")
                    continue
                return record
            next_page = self.driver.execute_script(
                """
                const table = jQuery('.dg'), instance = table.data('bootstrap.table');
                if (!instance || instance.options.sidePagination !== 'server') return false;
                const options = instance.options;
                const pages = Math.ceil(options.totalRows / options.pageSize);
                if (pages <= 1) return false;
                table.bootstrapTable('selectPage', options.pageNumber < pages ? options.pageNumber + 1 : 1);
                return true;
                """
            )
            if not next_page:
                return None

    def _is_record_still_unfinished(self, record_id: str) -> bool:
        records = self._wait_for_bootstrap_table_data(".dg")
        for record in records:
            if record.get("RecordID") == record_id:
                return not bool(record.get("IsSubmit"))
        return False

    def _wait_for_bootstrap_table_data(self, table_selector: str) -> list[dict]:
        timeout_at = time.monotonic() + 60
        while time.monotonic() < timeout_at:
            try:
                state = self.driver.execute_script(
                    """
                    const table = window.jQuery ? jQuery(arguments[0]) : null;
                    const instance = table && table.data('bootstrap.table');
                    if (!instance) return {ready: false};
                    const xhr = instance._xhr;
                    if (xhr && xhr.readyState === 4) {
                        if (xhr.status < 200 || xhr.status >= 400) {
                            return {ready: false, error: 'HTTP ' + xhr.status};
                        }
                        if (typeof xhr.state === 'function' && xhr.state() === 'rejected') {
                            return {ready: false, error: 'Invalid JSON or rejected table response'};
                        }
                        if (instance.options.sidePagination === 'server') {
                            const response = xhr.responseJSON;
                            const rows = response && response[instance.options.dataField || 'rows'];
                            const total = response && response[instance.options.totalField || 'total'];
                            if (!Array.isArray(rows) || total == null || !Number.isFinite(Number(total))) {
                                return {ready: false, error: 'Unexpected table response format'};
                            }
                        }
                    }
                    const loading = instance.$tableLoading && instance.$tableLoading.is(':visible');
                    const pending = instance.options.url && (!xhr || xhr.readyState !== 4);
                    return {
                        ready: !loading && !pending,
                        records: table.bootstrapTable('getData') || [],
                        pageNumber: instance.options.pageNumber
                    };
                    """,
                    table_selector,
                )
            except Exception:
                state = None
            if state and state.get("error"):
                raise RuntimeError(f"Course evaluation list failed to load: {state['error']}")
            if state and state.get("ready"):
                self._evaluation_page = int(state.get("pageNumber") or 1)
                return state.get("records") or []
            time.sleep(0.25)
        raise RuntimeError(f"Timed out waiting for bootstrap table data: {table_selector}")

    def _open_evaluation_record(self, record: dict) -> None:
        record_id = record.get("RecordID")
        if not record_id:
            raise RuntimeError("Course record is missing RecordID.")

        url = self._webvpn_app_url(f"/UMC_Evaluation/Reply?recordId={record_id}&type=1")
        self.driver.get(url)

        rewritten_url = rewrite_webvpn_app_url(
            self.driver.current_url,
            self.config["portal"].get("course_evaluation_url", ""),
        )
        if rewritten_url != self.driver.current_url:
            self.driver.get(rewritten_url)
        self._wait_for_evaluation_form()

    def _webvpn_app_url(self, app_path: str) -> str:
        base_url = self.driver.current_url
        if "/UMC_Evaluation/" not in base_url:
            base_url = self.config["portal"].get("course_evaluation_url", base_url)
        if "/UMC_Evaluation/" not in base_url:
            return app_path
        return base_url.split("/UMC_Evaluation/", 1)[0] + app_path

    def _check_last_radio_per_row(self) -> int:
        return int(self.driver.execute_script(last_radio_per_row_script()) or 0)

    def _wait_for_evaluation_form(self, timeout_seconds: int = 20) -> None:
        timeout_at = time.time() + timeout_seconds
        while time.time() < timeout_at:
            try:
                radio_count = self.driver.execute_script(
                    "return document.querySelectorAll(\"input[type='radio']\").length;"
                )
                if radio_count:
                    return
            except Exception:
                pass
            time.sleep(0.25)
        raise RuntimeError("Timed out waiting for evaluation form controls.")

    def _radio_row_status(self) -> dict:
        status = self.driver.execute_script(radio_row_status_script()) or {}
        return {
            "total": int(status.get("total") or 0),
            "checked": int(status.get("checked") or 0),
            "missing": int(status.get("missing") or 0),
        }

    def _fill_comment_fields(self, selectors: list[str], comment: str) -> int:
        filled = 0
        By = self._selenium["By"]
        for selector in unique_strings(selectors):
            for field in self.driver.find_elements(By.CSS_SELECTOR, selector):
                if not field.is_displayed():
                    continue
                current = field.get_attribute("value") or field.text or ""
                if current.strip():
                    continue
                field.clear()
                field.send_keys(comment)
                filled += 1
        return filled

    def _return_to_course_evaluation_list(self) -> None:
        page_number = getattr(self, "_evaluation_page", 1)
        url = self.config["portal"].get("course_evaluation_url")
        if url:
            self.driver.get(url)
        else:
            self.driver.back()
        self._wait_for_bootstrap_table_data(".dg")
        if page_number > 1:
            self.driver.execute_script(
                """
                const table = jQuery('.dg'), options = table.bootstrapTable('getOptions');
                const pages = Math.max(1, Math.ceil(options.totalRows / options.pageSize));
                table.bootstrapTable('selectPage', Math.min(arguments[0], pages));
                """,
                page_number,
            )
            self._wait_for_bootstrap_table_data(".dg")

    def _switch_to_frame_containing(self, by, value: str) -> None:
        self.driver.switch_to.default_content()
        try:
            self.driver.find_element(by, value)
            return
        except Exception:
            pass

        for iframe in self.driver.find_elements(self._selenium["By"].TAG_NAME, "iframe"):
            self.driver.switch_to.default_content()
            self.driver.switch_to.frame(iframe)
            try:
                self.driver.find_element(by, value)
                return
            except Exception:
                continue
        self.driver.switch_to.default_content()

    def _wait_for_browser_login_verification_if_present(self) -> bool:
        By = self._selenium["By"]
        EC = self._selenium["EC"]

        captcha_fallback_xpath = (
            "//input[@id='captcha'] | //input[@name='captcha'] | "
            "//input[contains(@placeholder, '验证码')] | //input[contains(@placeholder, '驗證碼')]"
        )
        image_xpath = self.selectors.get(
            "captcha_image_xpath",
            "//img[@id='captcha-img'] | //img[contains(@src, 'captcha')] | //img[contains(@onclick, 'captcha')]",
        )
        configured_input_xpath = self.selectors.get("captcha_input_xpath", captcha_fallback_xpath)
        input_xpath = f"({configured_input_xpath}) | ({captcha_fallback_xpath})"

        has_verification = False
        for xpath in (image_xpath, input_xpath):
            try:
                if any(element.is_displayed() for element in self.driver.find_elements(By.XPATH, xpath)):
                    has_verification = True
                    break
            except Exception:
                continue

        if not has_verification:
            print("No login verification field found.")
            return False

        self._print_page_state("02-login-verification-visible")
        print("Login verification field is visible.")
        solved = self._auto_solve_captcha()
        if solved:
            print("Login verification was filled automatically.")
            self._click_login_button()
            self._wait_until_webvpn_logged_in()
            return True

        try:
            self.wait.until(EC.element_to_be_clickable((By.XPATH, input_xpath))).click()
        except Exception:
            pass
        print("Complete login verification in Chrome and click login there.")
        self._wait_until_webvpn_logged_in()
        return True

        image_xpath = self.selectors.get(
            "captcha_image_xpath",
            "//img[@id='captcha-img'] | //img[contains(@src, 'captcha')] | //img[contains(@onclick, 'captcha')]",
        )
        input_xpath = self.selectors.get(
            "captcha_input_xpath",
            "//input[@id='captcha'] | //input[@name='captcha'] | "
            "//input[contains(@placeholder, '\u9a8c\u8bc1\u7801')] | //input[contains(@placeholder, '\u9a57\u8b49\u78bc')]",
        )

        has_verification = False
        try:
            self.wait.until(EC.visibility_of_element_located((By.XPATH, image_xpath)))
            has_verification = True
        except Exception:
            try:
                self.wait.until(EC.visibility_of_element_located((By.XPATH, input_xpath)))
                has_verification = True
            except Exception:
                pass

        if not has_verification:
            print("No login verification field found.")
            return False

        # --- 新增：自動識別驗證碼 ---

        solved = self._auto_solve_captcha() 
    # --- 自動識別驗證碼段落 ---

        solved = self._auto_solve_captcha() 
        
        if solved:

            # --- 新增：自動點擊登錄按鈕 ---
            try:
                login_btn_xpath = self.selectors.get("login_button_xpath")
                login_btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, login_btn_xpath)))
                
                # 稍微停 0.5 秒讓網頁反應一下，避免填完秒點導致無效
                import time
                time.sleep(0.5)
                
                login_btn.click()

            except Exception as e:
                print(f"   ⚠️ 自動點擊失敗，請手動點擊登錄: {e}")
        # -----------------------

        # 原有的提示依然保留，作為保險
        print("Login verification handled. Waiting for WebVPN session...")
        self._wait_until_webvpn_logged_in()
        return True
        # -----------------------

        try:
            self.wait.until(EC.element_to_be_clickable((By.XPATH, input_xpath))).click()
        except Exception:
            pass

        self._print_page_state("02-login-verification-visible")
        print("Login verification is visible. Complete it in Chrome and click login there.")
        self._wait_until_webvpn_logged_in()
        return True


    def _is_webvpn_logged_in(self) -> bool:
        self.driver.switch_to.default_content()
        current_url = urlsplit(self.driver.current_url or "")
        if current_url.hostname != "webvpn2.shsmu.edu.cn":
            return False
        if current_url.path not in ("", "/"):
            return False
        try:
            return bool(self.driver.execute_script(
                """
                function visible(element) {
                    const rect = element.getBoundingClientRect();
                    const style = getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none' && style.visibility !== 'hidden';
                }
                const links = Array.from(document.querySelectorAll('a'));
                return links.some(link => visible(link) && /教务系统|教務系統|jwstu\\.shsmu\\.edu\\.cn/i.test(link.innerText || ''))
                    && links.some(link => /^(注销|登出|退出|Logout|Sign out)$/i.test((link.innerText || '').trim()));
                """
            ))
        except Exception:
            return False

    def _is_login_form_visible(self) -> bool:
        try:
            username = self._wait_for_login_field("username", timeout_seconds=1)
            password = self._wait_for_login_field("password", timeout_seconds=1)
            return username.is_displayed() and password.is_displayed()
        except Exception:
            return False
        finally:
            self.driver.switch_to.default_content()

    def _wait_until_webvpn_logged_in(self, timeout_seconds: int | None = None) -> None:
        if timeout_seconds is None:
            timeout_seconds = self.config.get("portal", {}).get("manual_login_timeout_seconds", 1800)
        deadline = time.time() + timeout_seconds
        last_notice = 0.0

        while time.time() < deadline:
            if self._is_webvpn_logged_in():
                print("WebVPN login confirmed; continuing.")
                return

            current_url = self.driver.current_url or ""
            if "webvpn2.shsmu.edu.cn" not in current_url.lower() and not self._is_login_form_visible():
                self._print_page_state("login-unexpected-navigation")
                raise RuntimeError(f"Unexpected page during login: {current_url}")

            now = time.time()
            if now - last_notice > 10:
                print("Waiting for you to complete login in Chrome...")
                last_notice = now
            time.sleep(2)

        raise RuntimeError(f"WebVPN login was not confirmed after {timeout_seconds} seconds.")

    def _fill_captcha(self, answer: str) -> None:
        By = self._selenium["By"]
        EC = self._selenium["EC"]
        captcha_xpath = self.selectors.get(
            "captcha_input_xpath",
            "//input[@id='captcha'] | //input[@name='captcha'] | "
            "//input[contains(@placeholder, '\u9a8c\u8bc1\u7801')] | //input[contains(@placeholder, '\u9a57\u8b49\u78bc')]",
        )
        captcha_input = self.wait.until(EC.element_to_be_clickable((By.XPATH, captcha_xpath)))
        captcha_input.clear()
        captcha_input.send_keys(answer)

    def _click_login_button(self) -> None:
        By = self._selenium["By"]
        EC = self._selenium["EC"]
        fallback_xpath = (
            "//button[contains(., '\u767b\u5f55')] | //button[contains(., '\u767b\u5165')] | //button[contains(., '\u767b\u9304')] | "
            "//input[contains(@value, '\u767b\u5f55')] | //input[contains(@value, '\u767b\u5165')] | "
            "//input[contains(@class, 'login_box_landing')] | //a[contains(., '\u767b\u5f55')] | //a[contains(., '\u767b\u5165')] | "
            "//button[@type='submit'] | //input[@type='submit']"
        )
        configured_xpath = self.selectors.get("login_button_xpath", "")
        xpath = f"({configured_xpath}) | ({fallback_xpath})" if configured_xpath else fallback_xpath
        self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath))).click()

    def _click_xpath(self, xpath: str) -> None:
        By = self._selenium["By"]
        EC = self._selenium["EC"]
        self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath))).click()

    def _switch_to_newest_window(self, old_handles: set[str]) -> None:
        timeout_at = time.time() + 20
        while time.time() < timeout_at:
            handles = self.driver.window_handles
            new_handles = [handle for handle in handles if handle not in old_handles]
            if new_handles:
                self.driver.switch_to.window(new_handles[-1])
                return
            time.sleep(0.5)
        self.driver.switch_to.window(self.driver.window_handles[-1])

    def _close_duplicate_schedule_windows(self) -> None:
        handles = self.driver.window_handles
        if len(handles) <= 3:
            return
        active = handles[-1]
        for handle in handles[2:-1]:
            self.driver.switch_to.window(handle)
            self.driver.close()
        self.driver.switch_to.window(active)


def run_login_flow(config: dict) -> None:
    with LoginCopySession(config) as session:
        session.open_webvpn_to_schedule()


def run_evaluation_flow(config: dict) -> None:
    with LoginCopySession(config) as session:
        session.open_webvpn_to_course_evaluation()
        session.fill_all_course_evaluations()


if __name__ == "__main__":
    from app import main
    raise SystemExit(main())
