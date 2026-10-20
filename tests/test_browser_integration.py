"""Opt-in browser checks: RUN_BROWSER_TESTS=1 python -m unittest discover -s tests."""

import copy
import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

from logincopy import DEFAULT_CONFIG, LoginCopySession


@unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS') == '1', 'Opt-in local Chrome tests')
class BrowserIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jquery = urlopen('https://code.jquery.com/jquery-2.2.0.min.js', timeout=30).read()
        cls.bootstrap = urlopen(
            'https://cdnjs.cloudflare.com/ajax/libs/bootstrap-table/1.11.1/bootstrap-table.min.js',
            timeout=30,
        ).read()
        cls.posts = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def respond(self, content, kind='text/html', status=200):
                data = content if isinstance(content, bytes) else content.encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', kind + '; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = urlsplit(self.path)
                mode = parse_qs(path.query).get('recordId', ['success'])[0]
                if path.path == '/jquery.js':
                    return self.respond(cls.jquery, 'text/javascript')
                if path.path == '/bootstrap.js':
                    return self.respond(cls.bootstrap, 'text/javascript')
                if path.path == '/list':
                    table_mode = parse_qs(path.query).get('mode', ['pages'])[0]
                    return self.respond('''<!doctype html><meta charset="utf-8">
                        <script src="/jquery.js"></script><script src="/bootstrap.js"></script>
                        <table class="dg"></table><script>
                        jQuery('.dg').bootstrapTable({url:'/table?mode=%s', method:'post',
                          contentType:'application/x-www-form-urlencoded', sidePagination:'server',
                          pagination:true, pageSize:2, columns:[{field:'RecordID',title:'ID'}]});
                        </script>''' % table_mode)
                return self.respond('''<!doctype html><meta charset="utf-8">
                    <script src="/jquery.js"></script>
                    <form action="/UMC_Evaluation/Save" method="post">
                    <input type="hidden" name="fixture" value="%s">
                    <input id="SubmitState" name="SubmitState" value="0">
                    <button type="button" id="btnSure">Submit</button></form><script>
                    jQuery('#btnSure').on('click', function() {jQuery('form').submit();});
                    jQuery('form').on('submit', function(event) {
                      event.preventDefault();
                      jQuery.ajax({url:this.action, type:'POST', data:jQuery(this).serialize(),
                        dataType:'json', success:function(result) {
                          if (result.status === 'success') {
                            throw new Error('Reproduce page callback failure after server success');
                          }
                        }});
                    });</script>''' % mode)

            def do_POST(self):
                path = urlsplit(self.path)
                fields = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
                if path.path == '/table':
                    mode = parse_qs(path.query).get('mode', ['pages'])[0]
                    if mode == 'error':
                        return self.respond('{}', 'application/json', 500)
                    if mode == 'malformed':
                        return self.respond('<html>Authentication required</html>', 'application/json')
                    if mode == 'bad-shape':
                        return self.respond('{"message":"Authentication required"}', 'application/json')
                    rows = [] if mode == 'empty' else [
                        {'RecordID': 'done-1', 'IsSubmit': True, 'CourseType': 'Lab', 'CoursesContent': 'A'},
                        {'RecordID': 'done-2', 'IsSubmit': True, 'CourseType': 'Lab', 'CoursesContent': 'B'},
                        {'RecordID': 'todo-3', 'IsSubmit': False, 'CourseType': 'Lab', 'CoursesContent': 'C'},
                    ]
                    offset, limit = int(fields.get('offset', [0])[0]), int(fields.get('limit', [2])[0])
                    return self.respond(json.dumps({'total': len(rows), 'rows': rows[offset:offset + limit]}), 'application/json')
                mode = fields['fixture'][0]
                cls.posts.append(mode)
                if mode == 'slow':
                    time.sleep(0.7)
                result = {'status': 'error' if mode == 'error' else 'success', 'message': mode}
                self.respond(json.dumps(result), 'application/json')

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.daemon_threads = True
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'
        config = copy.deepcopy(DEFAULT_CONFIG)
        config['browser']['driver'] = os.environ.get('TEST_BROWSER', 'Chrome')
        config['download']['close_browser_on_finish'] = True
        config['evaluation']['submit'] = True
        config['evaluation']['submitTimeoutSeconds'] = 5
        cls.session = LoginCopySession(config)
        try:
            cls.session.__enter__()
        except BaseException:
            cls.server.shutdown()
            cls.server.server_close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__(None, None, None)
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=5)

    def open_form(self, mode):
        self.session.driver.get(self.origin + '/UMC_Evaluation/Reply?recordId=' + mode)

    def test_server_success_survives_page_callback_exception(self):
        self.open_form('success')
        started = time.monotonic()
        self.assertTrue(self.session.submit_evaluation())
        self.assertLess(time.monotonic() - started, 4)

    def test_server_rejection_does_not_count_as_success_or_retry(self):
        self.open_form('error')
        previous = self.posts.count('error')
        with self.assertRaisesRegex(RuntimeError, 'Submission rejected: error'):
            self.session.submit_evaluation()
        self.assertEqual(self.posts.count('error'), previous + 1)

    def test_slow_submission_waits_for_server_response(self):
        self.open_form('slow')
        started = time.monotonic()
        self.assertTrue(self.session.submit_evaluation())
        self.assertGreaterEqual(time.monotonic() - started, 0.7)

    def test_empty_loaded_bootstrap_table_finishes(self):
        self.session.driver.get(self.origin + '/list?mode=empty')
        self.assertEqual(self.session._wait_for_bootstrap_table_data('.dg'), [])
        self.assertIsNone(self.session._first_unfinished_student_course_record())

    def test_failed_bootstrap_request_is_an_error(self):
        self.session.driver.get(self.origin + '/list?mode=error')
        with self.assertRaisesRegex(RuntimeError, 'HTTP 500'):
            self.session._wait_for_bootstrap_table_data('.dg')

    def test_http_200_parse_failure_is_not_an_empty_table(self):
        self.session.driver.get(self.origin + '/list?mode=malformed')
        with self.assertRaisesRegex(RuntimeError, 'failed to load'):
            self.session._wait_for_bootstrap_table_data('.dg')

    def test_http_200_invalid_data_shape_is_not_an_empty_table(self):
        self.session.driver.get(self.origin + '/list?mode=bad-shape')
        with self.assertRaisesRegex(RuntimeError, 'failed to load'):
            self.session._wait_for_bootstrap_table_data('.dg')

    def test_scans_second_server_page_for_unfinished_course(self):
        self.session.driver.get(self.origin + '/list?mode=pages')
        record = self.session._first_unfinished_student_course_record()
        self.assertEqual(record['RecordID'], 'todo-3')
        self.assertEqual(self.session._evaluation_page, 2)

    def test_return_to_list_preserves_current_server_page(self):
        list_url = self.origin + '/list?mode=pages'
        self.session.driver.get(list_url)
        self.assertEqual(self.session._first_unfinished_student_course_record()['RecordID'], 'todo-3')
        self.open_form('success')
        old_url = self.session.config['portal']['course_evaluation_url']
        try:
            self.session.config['portal']['course_evaluation_url'] = list_url
            self.session._return_to_course_evaluation_list()
            self.assertEqual(self.session._evaluation_page, 2)
        finally:
            self.session.config['portal']['course_evaluation_url'] = old_url

    def test_missing_submit_response_times_out_without_retry(self):
        self.open_form('no-request')
        self.session.driver.execute_script("jQuery('#btnSure').off('click');")
        old_timeout = self.session.config['evaluation']['submitTimeoutSeconds']
        self.session.config['evaluation']['submitTimeoutSeconds'] = 0.4
        previous = len(self.posts)
        try:
            with self.assertRaisesRegex(RuntimeError, 'Timed out waiting for submission'):
                self.session.submit_evaluation()
            self.assertEqual(len(self.posts), previous)
        finally:
            self.session.config['evaluation']['submitTimeoutSeconds'] = old_timeout


if __name__ == '__main__':
    unittest.main()
