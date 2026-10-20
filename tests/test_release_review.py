import contextlib
import copy
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from logincopy import DEFAULT_CONFIG, LoginCopySession


class ReleaseReviewTests(unittest.TestCase):
    def preview(self):
        session = LoginCopySession(copy.deepcopy(DEFAULT_CONFIG))
        events = []
        record = {'RecordID': 'synthetic-record-id', 'CourseType': 'Lab', 'CoursesContent': 'Example'}
        session._first_unfinished_student_course_record = lambda seen: record
        session._open_evaluation_record = lambda record: None
        session._print_page_state = lambda step: None
        session.fill_evaluation_form = lambda: events.append('filled')
        session._return_to_course_evaluation_list = lambda: events.append('returned')
        return session, events

    def test_preview_waits_for_inspection_before_navigating_away(self):
        session, events = self.preview()
        def inspect(prompt):
            events.append('inspected')
            return ''
        with patch('builtins.input', side_effect=inspect):
            self.assertEqual(session.fill_all_course_evaluations(), 0)
        self.assertEqual(events, ['filled', 'inspected', 'returned'])

    def test_preview_with_no_input_keeps_the_filled_page_visible(self):
        session, events = self.preview()
        with patch('builtins.input', side_effect=EOFError):
            self.assertEqual(session.fill_all_course_evaluations(), 0)
        self.assertEqual(events, ['filled'])

    def test_unfinished_submission_error_does_not_expose_record_id(self):
        session, events = self.preview()
        session.config['evaluation']['submit'] = True
        session.config['evaluation']['maxCourses'] = 1
        session.submit_evaluation = lambda: True
        session._is_record_still_unfinished = lambda record_id: True
        with self.assertRaises(RuntimeError) as caught:
            session.fill_all_course_evaluations()
        self.assertNotIn('synthetic-record-id', str(caught.exception))

    def test_ocr_initialization_failure_returns_to_manual_verification(self):
        session = LoginCopySession(copy.deepcopy(DEFAULT_CONFIG))
        def unavailable(**kwargs):
            raise RuntimeError('Synthetic model initialization failure')
        with patch.dict('sys.modules', {'ddddocr': SimpleNamespace(DdddOcr=unavailable)}):
            self.assertFalse(session._auto_solve_captcha())


if __name__ == '__main__':
    unittest.main()
