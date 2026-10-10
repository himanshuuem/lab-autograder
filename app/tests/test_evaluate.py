import pytest

from autograder.evaluate import claimed_status, normalize, outputs_match


@pytest.mark.parametrize("a,e,mode,ok", [
    ("1 2 3\n", "1 2 3", "tokens", True),
    ("1  2\n3 \n\n", "1 2 3", "tokens", True),
    ("1 2 3", "1 2 4", "tokens", False),
    ("3.1415926", "3.14159260001", "tokens", True),
    ("3.14", "3.15", "tokens", False),
    ("1e3", "1000", "tokens", True),
    ("Sum = 7", "sum = 7", "tokens", False),
    ("1 2\n3", "1 2 3", "lines", False),
    ("1   2\n3  ", "1 2\n3", "lines", True),
    ("a \nb\n", "a\nb", "exact", True),
    ("a  b", "a b", "exact", False),
    ("", "", "tokens", True),
    ("", "0", "tokens", False),
])
def test_outputs_match(a, e, mode, ok):
    assert outputs_match(a, e, mode) is ok


def test_normalize():
    assert normalize("a \r\nb\r\n\n\n") == "a\nb"


@pytest.mark.parametrize("claimed,runs,status", [
    (None, [("1 2", "1 2")], "NONE"),
    ("1 2 3 4 9", [("1 2 3 4 9\n", "1 2 3 4 9")], "MATCHES_ACTUAL"),
    # terminal copy: typed input interleaved with the output
    ("Enter n: 5\n4 1 3 9 2\nSorted: 1 2 3 4 9", [("Enter n: Sorted: 1 2 3 4 9\n", "x")], "MATCHES_ACTUAL"),
    # wrong program, right answer pasted in the PDF
    ("1 2 3 4 9", [("9 4 3 2 1\n", "1 2 3 4 9")], "MATCHES_EXPECTED_ONLY"),
    ("10", [("", "10")], "MATCHES_EXPECTED_ONLY"),
    ("42", [("10\n", "10")], "NO_MATCH"),
    # short outputs must match contiguously, not as a scattered subsequence
    ("1 0 5", [("10\n", "10")], "NO_MATCH"),
])
def test_claimed_status(claimed, runs, status):
    assert claimed_status(claimed, runs) == status


@pytest.mark.parametrize("claimed,runs,status", [
    # OCR slips in words and lost spaces between digits are tolerated...
    ("3\nFact 11\nFact 2 2\nFact 3 6", [("Fact 1 1\nFact 2 2\nFact 3 6\n", "same")], "MATCHES_ACTUAL"),
    ("hello\nReversed: oLlleh", [("Reversed: olleh\n", "x")], "MATCHES_ACTUAL"),
    ("5\n41392\n12349", [("1 2 3 4 9\n", "1 2 3 4 9")], "MATCHES_ACTUAL"),
    # ...but numbers must be exact
    ("Sum = 7", [("Sum = 8\n", "Sum = 7")], "MATCHES_EXPECTED_ONLY"),
    ("Area = 12.75", [("Area = 12.57\n", "Area = 12.57")], "NO_MATCH"),
    ("1234\n10", [("9\n", "10")], "MATCHES_EXPECTED_ONLY"),
    ("Sorted: 1 2 3 4 9", [("Sorted: 9 4 3 2 1\n", "Sorted: 1 2 3 4 9")], "MATCHES_EXPECTED_ONLY"),
])
def test_claimed_status_from_screenshot(claimed, runs, status):
    assert claimed_status(claimed, runs, fuzzy=True) == status
