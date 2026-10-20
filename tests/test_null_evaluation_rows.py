import unittest
import contextlib
import io
from types import SimpleNamespace

from logincopy import is_null_evaluation_record
from logincopy import LoginCopySession


class NullEvaluationRowTests(unittest.TestCase):
    def test_skips_record_when_course_fields_are_null(self):
        record = {
            "RecordID": "null-record",
            "IsSubmit": False,
            "RecordToEvaluation": "Unit I",
            "CourseType": None,
            "CoursesContent": None,
        }

        self.assertTrue(is_null_evaluation_record(record))

    def test_skips_record_when_course_field_contains_literal_null(self):
        record = {
            "RecordID": "null-record",
            "IsSubmit": False,
            "RecordToEvaluation": "Unit I",
            "CourseType": "null",
            "CoursesContent": "null",
        }

        self.assertTrue(is_null_evaluation_record(record))

    def test_keeps_normal_unfinished_record(self):
        record = {
            "RecordID": "normal-record",
            "IsSubmit": False,
            "RecordToEvaluation": "Example teacher",
            "CourseType": "Lab",
            "CoursesContent": "Example course content",
        }

        self.assertFalse(is_null_evaluation_record(record))

    def test_finds_next_unfinished_record_after_null_row(self):
        records = [
            {
                "RecordID": "null-record",
                "IsSubmit": False,
                "RecordToEvaluation": "Unit I",
                "CourseType": None,
                "CoursesContent": None,
            },
            {
                "RecordID": "normal-record",
                "IsSubmit": False,
                "RecordToEvaluation": "Example teacher",
                "CourseType": "Lab",
                "CoursesContent": "Example course content",
            },
        ]
        session = LoginCopySession.__new__(LoginCopySession)
        session.driver = SimpleNamespace(
            execute_script=lambda _script: records,
        )
        session._wait_for_bootstrap_table_data = lambda _selector: records

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            selected = session._first_unfinished_student_course_record(set())

        self.assertEqual(selected["RecordID"], "normal-record")
        self.assertNotIn('null-record', output.getvalue())

    def test_course_evaluation_open_waits_for_table_data(self):
        session = LoginCopySession.__new__(LoginCopySession)
        session.config = {
            "portal": {
                "course_evaluation_url": "https://example.test/StudentCourseRecord",
            }
        }
        session.driver = SimpleNamespace(
            get=lambda _url: None,
        )
        waited_for = []
        session._wait_for_bootstrap_table_data = lambda selector: waited_for.append(selector)
        session._print_page_state = lambda _step: None

        session.open_course_evaluation()

        self.assertEqual(waited_for, [".dg"])

    def test_open_evaluation_record_waits_for_dynamic_form(self):
        session = LoginCopySession.__new__(LoginCopySession)
        session.config = {
            "portal": {
                "course_evaluation_url": "https://example.test/UMC_Evaluation/StudentCourseRecord",
            }
        }
        session.driver = SimpleNamespace(
            current_url=session.config["portal"]["course_evaluation_url"],
            get=lambda _url: None,
        )
        waited_for = []
        session._wait_for_evaluation_form = lambda: waited_for.append(True)

        session._open_evaluation_record({"RecordID": "normal-record"})

        self.assertEqual(waited_for, [True])


if __name__ == "__main__":
    unittest.main()
