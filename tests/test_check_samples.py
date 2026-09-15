"""check_samples must isolate every manifest case in its own fresh case database."""
import os
from scripts import check_samples


def test_each_case_runs_against_a_fresh_empty_db(monkeypatch, tmp_path):
    seen = []

    class _R:
        band, score, signals, evidence_path = "CLEAR", 0, [], None

    def fake_screen(inp, db_path):
        # A fresh DB exists (initialised) but holds no prior screenings.
        import sqlite3
        n = sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        seen.append((db_path, n))
        return _R()

    monkeypatch.setattr(check_samples, "screen", fake_screen)
    cases = [{"files": {"document": "a.jpg"}, "claimed": {}, "expect": "CLEAR"},
             {"files": {"document": "b.jpg"}, "claimed": {}, "expect": "CLEAR"}]
    results = check_samples.run_cases(cases, samples_dir=str(tmp_path),
                                      work_dir=str(tmp_path / "work"))
    assert len(results) == 2
    assert len({p for p, _ in seen}) == 2          # a distinct DB per case
    assert all(n == 0 for _, n in seen)            # each one empty
    assert not any(os.path.exists(p) for p, _ in seen)   # cleaned up afterwards
