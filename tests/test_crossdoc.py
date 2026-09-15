from app.engines import crossdoc

PASSPORT = {"source": "passport MRZ", "full_name": "ANNA MARIA ERIKSSON",
            "dob": "740812", "passport_no": "L898902C3", "nationality": "UTO"}

def test_consistent_documents_are_clean():
    visa = dict(PASSPORT, source="visa MRZ")
    signals = crossdoc.run([PASSPORT, visa])
    assert [s.code for s in signals] == ["XDOC_CONSISTENT"]

def test_passport_number_disagreement_is_critical():
    visa = dict(PASSPORT, source="visa MRZ", passport_no="X12345678")
    signals = crossdoc.run([PASSPORT, visa])
    hit = [s for s in signals if s.code == "XDOC_PASSPORT_NO_MISMATCH"]
    assert hit and hit[0].severity == "critical"

def test_dob_disagreement_is_flagged():
    visa = dict(PASSPORT, source="visa MRZ", dob="740813")
    assert "XDOC_DOB_MISMATCH" in [s.code for s in crossdoc.run([PASSPORT, visa])]

def test_name_order_and_case_do_not_count_as_mismatch():
    visa = dict(PASSPORT, source="visa MRZ", full_name="eriksson anna maria")
    assert "XDOC_NAME_MISMATCH" not in [s.code for s in crossdoc.run([PASSPORT, visa])]

def test_genuinely_different_name_is_flagged():
    visa = dict(PASSPORT, source="visa MRZ", full_name="JOHN PETER SMITH")
    assert "XDOC_NAME_MISMATCH" in [s.code for s in crossdoc.run([PASSPORT, visa])]

def test_missing_fields_are_not_treated_as_disagreement():
    sparse = {"source": "claimed", "full_name": "Anna Maria Eriksson"}
    codes = [s.code for s in crossdoc.run([PASSPORT, sparse])]
    assert "XDOC_DOB_MISMATCH" not in codes
    assert "XDOC_PASSPORT_NO_MISMATCH" not in codes

def test_single_source_emits_nothing():
    assert crossdoc.run([PASSPORT]) == []

def test_message_names_both_sources():
    visa = dict(PASSPORT, source="visa MRZ", dob="740813")
    hit = [s for s in crossdoc.run([PASSPORT, visa]) if s.code == "XDOC_DOB_MISMATCH"][0]
    assert "passport MRZ" in hit.message and "visa MRZ" in hit.message


# --- Controller ruling: dob normalisation across formats (YYMMDD vs ISO etc.) ---

def test_mrz_dob_vs_iso_claimed_dob_same_date_is_not_a_mismatch():
    claimed = {"source": "claimed", "full_name": "ANNA MARIA ERIKSSON",
               "dob": "1974-08-12"}
    codes = [s.code for s in crossdoc.run([PASSPORT, claimed])]
    assert "XDOC_DOB_MISMATCH" not in codes

def test_mrz_dob_vs_iso_claimed_dob_different_date_is_a_mismatch():
    claimed = {"source": "claimed", "full_name": "ANNA MARIA ERIKSSON",
               "dob": "1974-08-13"}
    codes = [s.code for s in crossdoc.run([PASSPORT, claimed])]
    assert "XDOC_DOB_MISMATCH" in codes

def test_unparseable_claimed_dob_is_treated_as_missing_not_a_mismatch():
    claimed = {"source": "claimed", "full_name": "ANNA MARIA ERIKSSON",
               "dob": "not a date"}
    codes = [s.code for s in crossdoc.run([PASSPORT, claimed])]
    assert "XDOC_DOB_MISMATCH" not in codes
