from app.engines import watchlist

def test_exact_match_is_flagged():
    signals = watchlist.run({"full_name": "Viktor Anatolyevich Petrov"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_reordered_name_still_matches():
    signals = watchlist.run({"full_name": "Petrov Viktor Anatolyevich"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_uppercase_exact_name_still_matches():
    signals = watchlist.run({"full_name": "VIKTOR ANATOLYEVICH PETROV"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_uppercase_reordered_name_still_matches():
    signals = watchlist.run({"full_name": "PETROV VIKTOR ANATOLYEVICH"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_minor_misspelling_matches():
    signals = watchlist.run({"full_name": "Dmitri Sokolovv"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_near_miss_is_review_not_match():
    signals = watchlist.run({"full_name": "Karin Lovisa Bergqvist"})
    codes = [s.code for s in signals]
    assert "WL_NEAR_MATCH" in codes and "WL_MATCH" not in codes


def test_demo_traveller_name_does_not_near_match_watchlist():
    """R1: the demo traveller Anna Maria Eriksson must not resemble any watchlist
    entry closely enough to trigger a medium/high/critical signal."""
    signals = watchlist.run({"full_name": "Anna Maria Eriksson"})
    assert not [s for s in signals if s.severity in ("medium", "high", "critical")]

def test_unrelated_name_is_clear():
    signals = watchlist.run({"full_name": "Jonathan Michael Brewster"})
    assert [s.code for s in signals] == ["WL_NO_MATCH"]

def test_missing_name_is_handled():
    assert watchlist.run({}) == []


# --- Task 20: extra name sources (passport MRZ, visa MRZ) ---

def test_extra_source_watchlisted_flags_with_source_named():
    """Typed name is clean but the passport MRZ carries a watchlisted name."""
    signals = watchlist.run(
        {"full_name": "Jonathan Michael Brewster"},
        extra_names={"passport MRZ": "Viktor Anatolyevich Petrov"},
    )
    matches = [s for s in signals if s.code == "WL_MATCH"]
    assert len(matches) == 1
    assert "passport MRZ" in matches[0].message


def test_typed_and_mrz_identical_produce_one_signal():
    signals = watchlist.run(
        {"full_name": "Viktor Anatolyevich Petrov"},
        extra_names={"passport MRZ": "Viktor Anatolyevich Petrov"},
    )
    matches = [s for s in signals if s.code == "WL_MATCH"]
    assert len(matches) == 1
    # Message should name both sources together.
    assert "claimed details" in matches[0].message
    assert "passport MRZ" in matches[0].message


def test_no_document_behaviour_unchanged():
    signals = watchlist.run({"full_name": "Viktor Anatolyevich Petrov"})
    assert "WL_MATCH" in [s.code for s in signals]


def test_visa_mrz_name_watchlisted():
    signals = watchlist.run(
        {"full_name": "Jonathan Michael Brewster"},
        extra_names={"visa MRZ": "Dmitri Sokolov"},
    )
    matches = [s for s in signals if s.code == "WL_MATCH"]
    assert len(matches) == 1
    assert "visa MRZ" in matches[0].message


def test_near_miss_on_document_name_is_medium():
    signals = watchlist.run(
        {"full_name": "Jonathan Michael Brewster"},
        extra_names={"passport MRZ": "Karin Lovisa Bergqvist"},
    )
    codes = [s.code for s in signals]
    assert "WL_NEAR_MATCH" in codes and "WL_MATCH" not in codes
    near = [s for s in signals if s.code == "WL_NEAR_MATCH"][0]
    assert "passport MRZ" in near.message


def test_clean_case_with_extra_names_single_info_signal():
    signals = watchlist.run(
        {"full_name": "Jonathan Michael Brewster"},
        extra_names={"passport MRZ": "Jonathan Michael Brewster",
                     "visa MRZ": "Jonathan Michael Brewster"},
    )
    assert [s.code for s in signals] == ["WL_NO_MATCH"]
