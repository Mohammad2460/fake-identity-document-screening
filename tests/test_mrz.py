import pytest
from app.engines import mrz

# Canonical ICAO Doc 9303 TD3 specimen
L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"

def test_check_digit_matches_icao_examples():
    assert mrz.check_digit("L898902C3") == 6
    assert mrz.check_digit("740812") == 2
    assert mrz.check_digit("120415") == 9

def test_check_digit_treats_filler_as_zero():
    assert mrz.check_digit("<<<") == 0

def test_parse_td3_extracts_fields():
    f = mrz.parse_td3(L1, L2)
    assert f["surname"] == "ERIKSSON"
    assert f["given_names"] == "ANNA MARIA"
    assert f["doc_number"] == "L898902C3"
    assert f["nationality"] == "UTO"
    assert f["dob"] == "740812"
    assert f["sex"] == "F"
    assert f["expiry"] == "120415"

def test_clean_mrz_emits_no_high_signals():
    signals = mrz.run([L1, L2], {"full_name": "ANNA MARIA ERIKSSON"})
    assert not [s for s in signals if s.severity in ("high", "critical")]

def test_tampered_document_number_is_detected():
    bad_l2 = "L898902C96UTO7408122F1204159ZE184226B<<<<<10"
    signals = mrz.run([L1, bad_l2], {})
    codes = [s.code for s in signals]
    assert "MRZ_DOCNUM_CHECKSUM_FAIL" in codes

def test_name_mismatch_against_claimed_identity():
    signals = mrz.run([L1, L2], {"full_name": "JOHN SMITH"})
    assert "MRZ_NAME_MISMATCH" in [s.code for s in signals]

def test_malformed_input_does_not_raise():
    signals = mrz.run(["garbage"], {})
    assert "MRZ_MALFORMED" in [s.code for s in signals]
