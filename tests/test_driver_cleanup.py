import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from logincopy import LoginCopySession


class FakeProcess:
    def __init__(self, running=True, terminate_error=None):
        self.running = running
        self.terminate_error = terminate_error
        self.terminate_called = False
        self.wait_called = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminate_called = True
        if self.terminate_error:
            raise self.terminate_error
        self.running = False

    def wait(self, timeout=None):
        self.wait_called = True
        self.running = False


class FakeService:
    def __init__(self, process):
        self.process = process


class DriverCleanupTests(unittest.TestCase):
    def _session_with_process(self, process):
        session = LoginCopySession.__new__(LoginCopySession)
        session.driver = type("FakeDriver", (), {"service": FakeService(process)})()
        session._chrome_process = None
        session._browser_profile_dir = None
        session.config = {"download": {"close_browser_on_finish": False}}
        return session

    def test_clears_finished_service_process_without_terminating_it(self):
        process = FakeProcess(running=False)
        session = self._session_with_process(process)

        session.__exit__(None, None, None)

        self.assertFalse(process.terminate_called)
        self.assertIsNone(session.driver.service.process)

    def test_ignores_invalid_windows_handle_and_clears_reference(self):
        process = FakeProcess(terminate_error=OSError(6, "invalid handle"))
        session = self._session_with_process(process)

        session.__exit__(None, None, None)

        self.assertTrue(process.terminate_called)
        self.assertIsNone(session.driver.service.process)


class BrowserLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(prefix="logincopy-cleanup-")))
        self.chrome_process = FakeProcess()
        self.service_process = FakeProcess()
        self.driver = Mock(service=FakeService(self.service_process))
        webdriver = Mock()
        webdriver.Chrome.side_effect = [
            RuntimeError("Direct Chrome startup failed; use the fallback."),
            self.driver,
        ]
        self.enterContext(patch.object(LoginCopySession, "_load_selenium", return_value={
            "webdriver": webdriver,
            "Options": Mock(),
            "Service": Mock(),
            "WebDriverWait": Mock(),
        }))
        self.enterContext(patch.object(
            LoginCopySession, "_resolve_chrome_binary", return_value="fake-chrome.exe"
        ))
        self.enterContext(patch.object(
            LoginCopySession, "_resolve_chromedriver_path", return_value=Path("chromedriver.exe")
        ))
        self.enterContext(patch.object(LoginCopySession, "_free_tcp_port", return_value=9222))
        self.debug_port_ready = self.enterContext(patch.object(
            LoginCopySession, "_wait_for_debug_port", return_value=True
        ))
        self.launch_browser = self.enterContext(patch(
            "logincopy.subprocess.Popen", return_value=self.chrome_process
        ))

    def _session(self, close_browser_on_finish):
        return LoginCopySession({
            "browser": {"user_data_parent_dir": str(self.root / "profiles")},
            "download": {
                "download_dir": str(self.root / "downloads"),
                "close_browser_on_finish": close_browser_on_finish,
            },
        })

    def _launched_profile(self):
        command = self.launch_browser.call_args.args[0]
        return Path(next(
            arg.split("=", 1)[1] for arg in command if arg.startswith("--user-data-dir=")
        ))

    def test_retains_manually_started_chrome_when_browser_should_stay_open(self):
        session = self._session(close_browser_on_finish=False)

        with session as entered:
            self.assertIs(entered, session)
            self.assertIs(session.driver, self.driver)
            self.assertIsNone(self.chrome_process.poll())

        self.assertIsNone(self.chrome_process.poll(), "Fallback Chrome must stay open.")
        self.assertFalse(self.chrome_process.terminate_called)
        self.assertFalse(self.chrome_process.wait_called)
        self.driver.quit.assert_not_called()
        self.assertIsNotNone(self.service_process.poll())
        self.assertIsNone(self.driver.service.process)

    def test_terminates_and_waits_for_fallback_chrome_when_close_is_requested(self):
        with self._session(close_browser_on_finish=True):
            profile = self._launched_profile()
            self.assertTrue(profile.is_dir())

        self.assertTrue(self.chrome_process.terminate_called)
        self.assertTrue(self.chrome_process.wait_called, "Chrome must be reaped after termination.")
        self.assertIsNotNone(self.chrome_process.poll())
        self.driver.quit.assert_called_once_with()
        self.assertIsNotNone(self.service_process.poll())
        self.assertIsNone(self.driver.service.process)
        self.assertFalse(profile.exists())

    def test_preserves_profile_used_by_retained_fallback_chrome(self):
        with self._session(close_browser_on_finish=False):
            profile = self._launched_profile()
            self.assertTrue((profile / "Default").is_dir())

        self.assertTrue(
            (profile / "Default").is_dir(),
            "The profile passed to Chrome must remain while Chrome is retained.",
        )
        self.assertIsNone(self.chrome_process.poll())

    def test_failed_enter_cleans_up_created_fallback_process_and_profile(self):
        self.debug_port_ready.return_value = False
        session = self._session(close_browser_on_finish=False)

        with self.assertRaisesRegex(RuntimeError, "Chrome could not be started for automation"):
            with session:
                self.fail("Startup must fail before entering the context body.")

        profile = self._launched_profile()
        self.assertTrue(self.chrome_process.terminate_called)
        self.assertTrue(self.chrome_process.wait_called)
        self.assertIsNotNone(self.chrome_process.poll())
        self.assertFalse(profile.exists(), "Failed __enter__ must not leave a temporary profile.")

    def test_runtime_failure_closes_browser_even_when_success_would_retain_it(self):
        with self.assertRaisesRegex(RuntimeError, 'synthetic runtime failure'):
            with self._session(close_browser_on_finish=False):
                profile = self._launched_profile()
                raise RuntimeError('synthetic runtime failure')
        self.assertTrue(self.chrome_process.terminate_called)
        self.assertFalse(profile.exists())
        self.driver.quit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
