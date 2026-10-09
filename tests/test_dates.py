from datetime import date
import pytest
from dates import resolve_deadline
POSTED = date(2026,10,12)

@pytest.mark.parametrize("phrase,expected,confirm", [
    ("bukas",date(2026,10,13),False), ("ngayon",POSTED,False), ("mamaya",POSTED,False),
    ("Friday",date(2026,10,16),False), ("next Friday",date(2026,10,23),True),
    ("Oct 16",date(2026,10,16),False), ("October 16",date(2026,10,16),False),
    ("10/16",date(2026,10,16),False), ("sa susunod na meeting",None,True),
    ("next week",None,True), (None,None,True), ("February 30",None,True),
    ("10/11",date(2026,10,11),True), ("2027-01-04",date(2027,1,4),False),
])
def test_resolution(phrase,expected,confirm):
    result = resolve_deadline(phrase, POSTED)
    assert result.deadline == expected
    assert result.needs_confirmation is confirm

@pytest.mark.parametrize("phrase", ["bukas","Friday","next Friday","Oct 16","10/16"])
def test_missing_anchor(phrase):
    result = resolve_deadline(phrase,None)
    assert result.deadline is None and result.needs_confirmation

@pytest.mark.parametrize("phrase", ["Oct 16 or Oct 23","not tomorrow","between Oct 16 and Oct 23"])
def test_ambiguous_candidates(phrase):
    result = resolve_deadline(phrase,POSTED)
    assert result.deadline is None and result.needs_confirmation
