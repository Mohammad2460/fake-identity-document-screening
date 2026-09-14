from app.engines import identity

def test_passport_number_format():
    assert identity.passport_number_plausible("L898902C3") is True
    assert identity.passport_number_plausible("AB1") is False
    assert identity.passport_number_plausible("!!!!###") is False

def test_clean_identity_produces_no_high_signals():
    signals = identity.run({
        "full_name": "Anna Maria Eriksson", "dob": "1974-08-12",
        "passport_no": "L898902C3", "nationality": "UTO",
        "email": "anna.eriksson@gmail.com", "phone": "9845012763",
    })
    assert not [s for s in signals if s.severity in ("high", "critical")]

def test_disposable_email_flagged():
    signals = identity.run({"email": "throwaway@mailinator.com"})
    assert "ID_DISPOSABLE_EMAIL" in [s.code for s in signals]

def test_implausible_dob_flagged():
    assert "ID_DOB_IMPLAUSIBLE" in [s.code for s in identity.run({"dob": "2025-01-01"})]
    assert "ID_DOB_IMPLAUSIBLE" in [s.code for s in identity.run({"dob": "1890-01-01"})]

def test_unparseable_dob_flagged():
    assert "ID_DOB_UNPARSEABLE" in [s.code for s in identity.run({"dob": "not a date"})]

def test_keyboard_pattern_name_flagged():
    signals = identity.run({"full_name": "Asdf Qwerty"})
    assert "ID_NAME_SUSPICIOUS" in [s.code for s in signals]

def test_single_token_name_is_low_severity():
    signals = identity.run({"full_name": "Madonna"})
    assert "ID_NAME_SINGLE_TOKEN" in [s.code for s in signals]

def test_sequential_phone_flagged():
    signals = identity.run({"phone": "1234567890"})
    assert "ID_PHONE_SEQUENTIAL" in [s.code for s in signals]

def test_descending_phone_flagged():
    signals = identity.run({"phone": "9876543210"})
    assert "ID_PHONE_SEQUENTIAL" in [s.code for s in signals]

def test_realistic_phone_not_flagged():
    signals = identity.run({"phone": "9845012763"})
    assert "ID_PHONE_SEQUENTIAL" not in [s.code for s in signals]

def test_repeated_digit_phone_flagged():
    signals = identity.run({"phone": "9999999999"})
    assert "ID_PHONE_SEQUENTIAL" in [s.code for s in signals]

def test_email_name_divergence_flagged():
    signals = identity.run({"full_name": "Anna Eriksson", "email": "xk92mzq7@gmail.com"})
    assert "ID_EMAIL_NAME_DIVERGENCE" in [s.code for s in signals]

def test_malformed_passport_number_flagged():
    signals = identity.run({"passport_no": "!!"})
    assert "ID_PASSPORT_FORMAT_ODD" in [s.code for s in signals]
