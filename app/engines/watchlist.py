"""Fuzzy screening of the claimed name against a sanctions / PEP list."""
import csv
import functools
from rapidfuzz import fuzz, process
from app.models import Signal

MATCH_THRESHOLD = 88
REVIEW_THRESHOLD = 78

@functools.lru_cache(maxsize=4)
def load_watchlist(path: str = "data/watchlist.csv") -> tuple:
    with open(path, newline="", encoding="utf-8") as fh:
        return tuple(dict(row) for row in csv.DictReader(fh))

def run(claimed: dict, path: str = "data/watchlist.csv") -> list[Signal]:
    name = (claimed.get("full_name") or "").strip()
    if not name:
        return []

    entries = load_watchlist(path)
    names = [e["name"] for e in entries]
    best = process.extractOne(name, names, scorer=fuzz.token_sort_ratio)
    if best is None:
        return [Signal(code="WL_NO_MATCH", engine="watchlist", severity="info",
                       message="No sanctions or PEP list entry resembles this name.")]

    matched_name, score, idx = best
    entry = entries[idx]
    ev = {"matched": matched_name, "score": round(score, 1),
          "list": entry["list"], "country": entry["country"], "reason": entry["reason"]}

    if score >= MATCH_THRESHOLD:
        return [Signal(
            code="WL_MATCH", engine="watchlist", severity="critical",
            message=(f"Claimed name matches {matched_name!r} on the {entry['list']} list "
                     f"({entry['reason']}, {entry['country']}) at {score:.0f}% similarity."),
            evidence=ev,
        )]
    if score >= REVIEW_THRESHOLD:
        return [Signal(
            code="WL_NEAR_MATCH", engine="watchlist", severity="medium",
            message=(f"Claimed name is a partial match ({score:.0f}%) to {matched_name!r} "
                     f"on the {entry['list']} list. Manual analyst review required."),
            evidence=ev,
        )]
    return [Signal(code="WL_NO_MATCH", engine="watchlist", severity="info",
                   message=f"No watchlist entry above {REVIEW_THRESHOLD}% similarity "
                           f"(closest: {matched_name!r} at {score:.0f}%).", evidence=ev)]
