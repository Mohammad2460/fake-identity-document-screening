import pytest
from app import db


@pytest.fixture
def dbfile(tmp_path):
    p = str(tmp_path / "t.db")
    db.init_db(p)
    return p


def test_phone_and_email_are_normalised_for_matching(dbfile):
    db.save_case(
        dbfile, "c1",
        {"full_name": "Anna Eriksson", "phone": "+91 98765 43210",
         "email": "Anna@Example.com"},
        10, "CLEAR", [],
    )
    by_phone = db.find_prior(dbfile, phone="919876543210")
    by_email = db.find_prior(dbfile, email="anna@example.com")
    assert [r["case_id"] for r in by_phone] == ["c1"]
    assert [r["case_id"] for r in by_email] == ["c1"]
