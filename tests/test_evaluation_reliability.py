import contextlib
import copy
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from logincopy import DEFAULT_CONFIG, LoginCopySession


class EvaluationReliabilityTests(unittest.TestCase):
    def session(self):
        return LoginCopySession(copy.deepcopy(DEFAULT_CONFIG))

    def loop_session(self, count):
        session = self.session()
        session.config['evaluation']['submit'] = True
        records = [
            {'RecordID': str(i), 'IsSubmit': False,
             'CourseType': 'Lab', 'CoursesContent': 'Example'}
            for i in range(count)
        ]
        session._first_unfinished_student_course_record = lambda _seen: next(
            (record for record in records if not record['IsSubmit']), None
        )
        current = []
        session._open_evaluation_record = lambda record: current.append(record)
        session._print_page_state = lambda _step: None
        session.fill_evaluation_form = lambda: None

        def submit():
            current[-1]['IsSubmit'] = True
            return True

        session.submit_evaluation = submit
        session._return_to_course_evaluation_list = lambda: None
        session._is_record_still_unfinished = lambda _record_id: False
        return session, records

    def test_default_run_completes_more_than_thirty_records(self):
        session, records = self.loop_session(31)
        with contextlib.redirect_stdout(io.StringIO()):
            completed = session.fill_all_course_evaluations()
        self.assertEqual(completed, 31)
        self.assertTrue(all(record['IsSubmit'] for record in records))

    def test_explicit_limit_reports_unfinished_work(self):
        session, records = self.loop_session(3)
        session.config['evaluation']['maxCourses'] = 2
        with contextlib.redirect_stdout(io.StringIO()) as output:
            completed = session.fill_all_course_evaluations()
        self.assertEqual(completed, 2)
        self.assertFalse(records[2]['IsSubmit'])
        self.assertIn('limit', output.getvalue().lower())
        self.assertIn('unfinished', output.getvalue().lower())

    def test_empty_loaded_table_returns_empty_records(self):
        session = self.session()
        session.driver = SimpleNamespace(execute_script=lambda *_args: {
            'ready': True, 'records': [], 'error': None,
        })
        with patch('logincopy.time.sleep'), patch(
            'logincopy.time.monotonic', side_effect=[0, 0, 21]
        ), patch('logincopy.time.time', side_effect=[0, 0, 21]):
            self.assertEqual(session._wait_for_bootstrap_table_data('.dg'), [])

    def test_loading_table_is_not_mistaken_for_empty_loaded_table(self):
        session = self.session()
        states = iter([
            {'ready': False, 'records': [], 'error': None},
            {'ready': True, 'records': [{'RecordID': 'ready'}], 'error': None},
        ])
        session.driver = SimpleNamespace(execute_script=lambda *_args: next(states))
        with patch('logincopy.time.sleep'):
            self.assertEqual(
                session._wait_for_bootstrap_table_data('.dg'),
                [{'RecordID': 'ready'}],
            )

    def test_table_load_error_is_not_reported_as_empty_success(self):
        session = self.session()
        session.driver = SimpleNamespace(execute_script=lambda *_args: {
            'ready': False, 'records': [], 'error': 'HTTP 500',
        })
        with self.assertRaisesRegex(RuntimeError, 'HTTP 500'):
            session._wait_for_bootstrap_table_data('.dg')

    def test_auth_page_without_inputs_is_not_logged_in(self):
        session = self.session()
        session.driver = SimpleNamespace(
            current_url='https://webvpn2.shsmu.edu.cn/https/auth/ac/#/index',
            switch_to=SimpleNamespace(default_content=lambda: None),
            execute_script=lambda *_args: False,
        )
        session._is_login_form_visible = lambda: False
        self.assertFalse(session._is_webvpn_logged_in())

    def test_blank_portal_root_is_not_logged_in(self):
        session = self.session()
        session.driver = SimpleNamespace(
            current_url='https://webvpn2.shsmu.edu.cn/',
            switch_to=SimpleNamespace(default_content=lambda: None),
            execute_script=lambda *_args: False,
        )
        session._is_login_form_visible = lambda: False
        self.assertFalse(session._is_webvpn_logged_in())

    def test_submit_waits_for_completion_instead_of_fixed_delay(self):
        session = self.session()
        session.config['evaluation']['submit'] = True
        session.driver = SimpleNamespace(current_url='https://example.test/Reply?recordId=one')
        session._print_submit_diagnostics = lambda: None
        session._click_submit_control = lambda: {'clicked': True}
        session._wait_for_submission = Mock(return_value=None)
        session._accept_possible_alert = lambda **_kwargs: None
        with contextlib.redirect_stdout(io.StringIO()), patch('logincopy.time.sleep') as sleep:
            self.assertTrue(session.submit_evaluation())
        session._wait_for_submission.assert_called_once()
        sleep.assert_not_called()

    def test_submission_rejection_is_propagated_without_retry(self):
        session = self.session()
        session.config['evaluation']['submit'] = True
        session.driver = SimpleNamespace(current_url='https://example.test/Reply?recordId=one')
        session._print_submit_diagnostics = lambda: None
        clicks = []
        session._click_submit_control = lambda: clicks.append(True) or {'clicked': True}
        session._wait_for_submission = Mock(side_effect=RuntimeError('Submission rejected'))
        session._accept_possible_alert = lambda **_kwargs: None
        with contextlib.redirect_stdout(io.StringIO()), patch('logincopy.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Submission rejected'):
                session.submit_evaluation()
        self.assertEqual(len(clicks), 1)


if __name__ == '__main__':
    unittest.main()
