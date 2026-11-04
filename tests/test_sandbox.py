from code_health_evals.models import Case, Label
from code_health_evals.sandbox import label_coverage, outcome, parse_results, pytest_cmd

PYTEST_RA = """
==================================== PASSES ====================================
=========================== short test summary info ============================
PASSED testing/test_skipping.py::TestEvaluation::test_no_marker
FAILED testing/test_skipping.py::test_dynamic_xfail_set_during_runtest_failed - assert 0
ERROR testing/test_skipping.py::test_broken
"""


def test_parse_results():
    assert parse_results(PYTEST_RA) == {
        "testing/test_skipping.py::TestEvaluation::test_no_marker": "PASSED",
        "testing/test_skipping.py::test_dynamic_xfail_set_during_runtest_failed": "FAILED",
        "testing/test_skipping.py::test_broken": "ERROR",
    }


def test_label_coverage_flags_missed_and_non_executable_ranges():
    case = Case(
        id="x", slice="fresh", repo="r", title="t", diff="",
        labels=[
            Label(file="src/a.py", start_line=10, end_line=13, description="d"),
            Label(file="src/a.py", start_line=20, end_line=21, description="blank lines only"),
        ],
    )
    cov = {"files": {"src/a.py": {"executed_lines": [10, 11], "missing_lines": [13, 30]}}}
    assert label_coverage(case, cov) == [
        {"file": "src/a.py", "range": [10, 13], "executable": 3, "missed": [13]},
        # no executable line in 20-21: judged by the statement above it, line 13, never run
        {"file": "src/a.py", "range": [20, 21], "executable": 1, "statement": 13, "missed": [13]},
    ]
    assert label_coverage(case, {"files": {}})[0]["executable"] == 0  # file never imported


def test_outcome_rolls_up_parametrized_runs():
    res = {"t.py::a[x]": "PASSED", "t.py::a[y]": "FAILED", "t.py::b": "PASSED"}
    assert outcome(res, "t.py::a") == "FAILED"
    assert outcome(res, "t.py::b") == "PASSED"
    assert outcome(res, "t.py::c") == "MISSING"


def test_pytest_cmd_quotes_ids():
    cmd = pytest_cmd(["t.py::test_a[x y]"], "src")
    assert "'t.py::test_a[x y]'" in cmd and cmd.endswith("-o /tmp/cov.json") and "--rcfile=/tmp/covrc" in cmd
