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

def test_hyphenated_name_is_not_falsely_flagged():
    signals = mrz.run([L1, L2], {"full_name": "Anna-Maria Eriksson"})
    assert "MRZ_NAME_MISMATCH" not in [s.code for s in signals]

def test_truncated_mrz_surname_matches_full_claimed_name():
    assert mrz.names_match(
        ["ANNA", "MARIA", "ERIKSSONOVICH"], ["ERIKSSONOV", "ANNA", "MARIA"]
    )

def test_malformed_input_does_not_raise():
    signals = mrz.run(["garbage"], {})
    assert "MRZ_MALFORMED" in [s.code for s in signals]

def test_lowercase_characters_are_normalised():
    lower_l2 = L2.lower()
    signals = mrz.run([L1, lower_l2], {"full_name": "ANNA MARIA ERIKSSON"})
    assert not [s for s in signals if s.severity in ("high", "critical")]

def test_invalid_character_returns_malformed_not_raise():
    bad_l2 = "L898902C#6UTO7408122F1204159ZE184226B<<<<<10"
    signals = mrz.run([L1, bad_l2], {})
    codes = [s.code for s in signals]
    assert codes == ["MRZ_MALFORMED"]
    assert signals[0].severity == "medium"
    assert "#" in signals[0].message

def test_specimen_passes_composite_and_personal_checks():
    signals = mrz.run([L1, L2], {"full_name": "ANNA MARIA ERIKSSON"})
    codes = [s.code for s in signals]
    assert "MRZ_COMPOSITE_CHECKSUM_FAIL" not in codes
    assert "MRZ_PERSONAL_CHECKSUM_FAIL" not in codes

def test_final_check_digit_altered_is_detected():
    bad_l2 = L2[:43] + "9"
    signals = mrz.run([L1, bad_l2], {})
    codes = [s.code for s in signals]
    assert "MRZ_COMPOSITE_CHECKSUM_FAIL" in codes
    for s in signals:
        if s.code == "MRZ_COMPOSITE_CHECKSUM_FAIL":
            assert s.severity == "high"

def test_dob_and_its_own_check_digit_forged_together_still_caught():
    # NOTE: the fix brief's literal example ("740813", changing only the DOB's
    # last digit) does not trigger a composite failure: for this TD3 layout the
    # composite weight applied to the DOB's last digit (7) plus the composite
    # weight applied to its own recomputed check digit (3) sum to 10 === 0 mod 10,
    # so that specific single-digit forgery is invariant under the composite
    # check by mathematical coincidence (verified empirically). "740912"
    # (changing the DOB's 4th digit instead) exercises the same intent -- a
    # field and its own check digit forged together, caught only by the
    # composite check -- and does trigger MRZ_COMPOSITE_CHECKSUM_FAIL.
    forged_dob = "740912"
    forged_dob_cd = str(mrz.check_digit(forged_dob))
    forged_l2 = L2[:13] + forged_dob + forged_dob_cd + L2[20:]
    signals = mrz.run([L1, forged_l2], {})
    codes = [s.code for s in signals]
    assert "MRZ_COMPOSITE_CHECKSUM_FAIL" in codes
    assert "MRZ_DOB_CHECKSUM_FAIL" not in codes


# --- task-16b item 2: OCR output of a genuine rendered MRZ must parse cleanly ---
OCR_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<"                    # trailing fillers dropped
OCR_L2 = "L898902C36UT07408122F3012316<<<<<<<<<<<<<<06"    # nationality O read as 0


def test_normalise_pads_line1_whose_trailing_fillers_ocr_dropped():
    l1, _ = mrz.normalise_td3([OCR_L1, OCR_L2])
    assert len(l1) == 44 and l1.startswith(OCR_L1) and set(l1[28:]) == {"<"}


def test_normalise_repairs_digit_letter_confusion_by_field_type():
    _, l2 = mrz.normalise_td3([OCR_L1, OCR_L2])
    assert l2[10:13] == "UTO"
    # alphanumeric document number untouched; numeric fields repaired the other way
    _, l2b = mrz.normalise_td3([OCR_L1, "L898902C36UTO74O8122F3O12316<<<<<<<<<<<<<<06"])
    assert l2b[0:9] == "L898902C3" and l2b[13:19] == "740812" and l2b[21:27] == "301231"


def test_normalise_does_not_pad_a_line1_cut_mid_name():
    l1, _ = mrz.normalise_td3(["P<UTOERIKSSON<<ANNA<MAR", OCR_L2])
    assert l1 == "P<UTOERIKSSON<<ANNA<MAR"


def test_ocr_read_genuine_mrz_passes_all_checks():
    sigs = mrz.run([OCR_L1, OCR_L2], {"full_name": "Anna Maria Eriksson"})
    assert [s.code for s in sigs] == ["MRZ_ALL_CHECKS_PASS"]
    assert sigs[0].evidence["nationality"] == "UTO"


def test_normalisation_does_not_hide_an_altered_document_number():
    bad = "L899902C36UT07408122F3012316<<<<<<<<<<<<<<06"
    assert "MRZ_DOCNUM_CHECKSUM_FAIL" in [s.code for s in mrz.run([OCR_L1, bad], {})]
