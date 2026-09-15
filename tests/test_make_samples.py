"""R7: build_mrz's personal-number field must itself be checksum-valid."""
from app.engines import mrz
from scripts.make_samples import build_mrz


def test_build_mrz_with_personal_field_has_no_checksum_failures():
    l1, l2 = build_mrz("V", "ERIKSSON", "ANNA MARIA", "V10293847", "UTO",
                        "740812", "F", "301231", personal="L898902C3")
    signals = mrz.run([l1, l2], {})
    codes = [s.code for s in signals if s.code.startswith("MRZ_") and s.code.endswith("FAIL")]
    assert codes == []


def test_build_mrz_personal_field_round_trips_through_parse_td3():
    l1, l2 = build_mrz("V", "ERIKSSON", "ANNA MARIA", "V10293847", "UTO",
                        "740812", "F", "301231", personal="X47281956")
    parsed = mrz.parse_td3(l1, l2)
    assert parsed["personal_number"].replace(mrz.FILLER, "") == "X47281956"


def test_build_mrz_without_personal_field_is_unchanged():
    l1, l2 = build_mrz("P", "ERIKSSON", "ANNA MARIA", "L898902C3", "UTO",
                        "740812", "F", "301231")
    signals = mrz.run([l1, l2], {})
    codes = [s.code for s in signals if s.code.startswith("MRZ_") and s.code.endswith("FAIL")]
    assert codes == []
    parsed = mrz.parse_td3(l1, l2)
    assert parsed["personal_number"].replace(mrz.FILLER, "") == ""
