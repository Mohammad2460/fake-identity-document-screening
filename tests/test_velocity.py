import pytest
from app import db
from app.engines import velocity

@pytest.fixture
def dbfile(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return p

def test_first_submission_is_clean(dbfile):
    signals = velocity.run({"passport_no": "L898902C3", "email": "a@b.com"}, None, dbfile)
    assert [s.severity for s in signals] == ["info"]

def test_same_id_different_name_is_flagged(dbfile):
    db.save_case(dbfile, "c1", {"passport_no": "L898902C3", "full_name": "Anna Eriksson"},
                 10, "CLEAR", [])
    signals = velocity.run({"passport_no": "L898902C3", "full_name": "John Smith"}, None, dbfile)
    assert "VEL_ID_REUSED_NEW_NAME" in [s.code for s in signals]

def test_same_id_same_name_is_only_informational(dbfile):
    db.save_case(dbfile, "c1", {"passport_no": "L898902C3", "full_name": "Anna Eriksson"},
                 10, "CLEAR", [])
    signals = velocity.run({"passport_no": "L898902C3", "full_name": "Anna Eriksson"}, None, dbfile)
    assert "VEL_ID_REUSED_NEW_NAME" not in [s.code for s in signals]

def test_identical_document_hash_is_flagged(dbfile):
    db.save_case(dbfile, "c1", {"full_name": "A"}, 10, "CLEAR", [], doc_hash="deadbeef")
    signals = velocity.run({"full_name": "B"}, "deadbeef", dbfile)
    assert "VEL_DUPLICATE_DOCUMENT" in [s.code for s in signals]

def test_burst_of_submissions_is_flagged(dbfile):
    for i in range(6):
        db.save_case(dbfile, f"c{i}", {"email": f"u{i}@x.com"}, 10, "CLEAR", [])
    signals = velocity.run({"email": "u99@x.com"}, None, dbfile)
    assert "VEL_SUBMISSION_BURST" in [s.code for s in signals]
