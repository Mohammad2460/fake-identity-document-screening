from app.engines import watchlist

def test_exact_match_is_flagged():
    signals = watchlist.run({"full_name": "Viktor Anatolyevich Petrov"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_reordered_name_still_matches():
    signals = watchlist.run({"full_name": "Petrov Viktor Anatolyevich"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_minor_misspelling_matches():
    signals = watchlist.run({"full_name": "Dmitri Sokolovv"})
    assert "WL_MATCH" in [s.code for s in signals]

def test_near_miss_is_review_not_match():
    signals = watchlist.run({"full_name": "Anna Maria Eriksson"})
    codes = [s.code for s in signals]
    assert "WL_NEAR_MATCH" in codes and "WL_MATCH" not in codes

def test_unrelated_name_is_clear():
    signals = watchlist.run({"full_name": "Jonathan Michael Brewster"})
    assert [s.code for s in signals] == ["WL_NO_MATCH"]

def test_missing_name_is_handled():
    assert watchlist.run({}) == []
