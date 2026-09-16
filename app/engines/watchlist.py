"""Fuzzy screening of every available name source against a sanctions / PEP list.

Sources: the claimed (typed) name, plus any extra sources the caller supplies -
typically the passport MRZ name and the visa MRZ name. A wanted traveller whose
passport prints a watchlisted name must be caught even if the officer types
something else at intake (task-20).
"""
import csv
import functools
import os
import rapidfuzz
from rapidfuzz import fuzz, process
from app.models import Signal

MATCH_THRESHOLD = 88
REVIEW_THRESHOLD = 78

def _read(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def local_overlay_path(path: str) -> str:
    """watchlist.csv -> watchlist.local.csv, alongside it."""
    base, ext = os.path.splitext(path)
    return base + ".local" + ext


@functools.lru_cache(maxsize=4)
def load_watchlist(path: str = "data/watchlist.csv") -> tuple:
    """The committed list, plus an optional gitignored overlay beside it.

    The overlay exists so a name that must never be committed - a consenting
    teammate standing in for a wanted traveller during the demo - can be
    screened without shipping a real person as a sanctioned individual.
    """
    entries = _read(path)
    overlay = local_overlay_path(path)
    if os.path.exists(overlay):
        entries += _read(overlay)
    return tuple(entries)


def _normalise(name: str) -> str:
    return " ".join(name.strip().upper().split())


def _sources(claimed: dict, extra_names: dict[str, str] | None) -> list[tuple[str, str]]:
    """[(source_label, name)] for every non-empty name source, claimed first."""
    out = []
    claimed_name = (claimed.get("full_name") or "").strip()
    if claimed_name:
        out.append(("claimed details", claimed_name))
    for label, name in (extra_names or {}).items():
        name = (name or "").strip()
        if name:
            out.append((label, name))
    return out


def _combine_labels(labels: list[str]) -> str:
    """Join source labels into a readable phrase, e.g. 'claimed details and the
    passport MRZ' or 'the passport MRZ and the visa MRZ'."""
    phrased = [lbl if lbl == "claimed details" else f"the {lbl}" for lbl in labels]
    if len(phrased) == 1:
        return phrased[0]
    return ", ".join(phrased[:-1]) + f" and {phrased[-1]}"


def run(claimed: dict, path: str = "data/watchlist.csv",
        extra_names: dict[str, str] | None = None) -> list[Signal]:
    sources = _sources(claimed, extra_names)
    if not sources:
        return []

    entries = load_watchlist(path)
    names = [e["name"] for e in entries]

    # Best match per distinct (normalised) name, keeping the source labels that
    # produced it so duplicate names collapse into one signal.
    by_name: dict[str, dict] = {}
    for label, raw_name in sources:
        key = _normalise(raw_name)
        if key not in by_name:
            by_name[key] = {"display": raw_name, "labels": []}
        by_name[key]["labels"].append(label)

    overall_best = None  # (score, matched_name, entry) across all sources, for the info signal

    result_signals: list[Signal] = []
    for key, info in by_name.items():
        display_name = info["display"]
        labels = info["labels"]
        best = process.extractOne(display_name, names, scorer=fuzz.token_sort_ratio,
                                  processor=rapidfuzz.utils.default_process)
        if best is None:
            continue
        matched_name, score, idx = best
        entry = entries[idx]

        if overall_best is None or score > overall_best[0]:
            overall_best = (score, matched_name, entry)

        if score < REVIEW_THRESHOLD:
            continue

        ev = {"matched": matched_name, "score": round(score, 1),
              "list": entry["list"], "country": entry["country"], "reason": entry["reason"],
              "sources": labels}
        source_phrase = _combine_labels(labels)

        if score >= MATCH_THRESHOLD:
            result_signals.append(Signal(
                code="WL_MATCH", engine="watchlist", severity="critical",
                message=(f"The name in {source_phrase} ({display_name!r}) matches "
                         f"{matched_name!r} on the {entry['list']} list "
                         f"({entry['reason']}, {entry['country']}) at {score:.0f}% similarity."),
                plain=(f"This name, {display_name}, is on a sanctions list "
                       f"({entry['list']}). A match this close needs an officer's "
                       f"decision before the traveller is admitted."),
                evidence=ev,
            ))
        else:
            result_signals.append(Signal(
                code="WL_NEAR_MATCH", engine="watchlist", severity="medium",
                message=(f"The name in {source_phrase} ({display_name!r}) is a partial "
                         f"match ({score:.0f}%) to {matched_name!r} on the {entry['list']} "
                         f"list. Manual analyst review required."),
                plain=(f"This name, {display_name}, is a partial match to a name "
                       f"on the {entry['list']} sanctions list. An officer should "
                       f"take a closer look."),
                evidence=ev,
            ))

    if result_signals:
        return result_signals

    if overall_best is None:
        return [Signal(code="WL_NO_MATCH", engine="watchlist", severity="info",
                       message="No sanctions or PEP list entry resembles this name.",
                       plain="This name does not resemble anyone on a sanctions "
                             "or watch list.")]

    score, matched_name, entry = overall_best
    ev = {"matched": matched_name, "score": round(score, 1),
          "list": entry["list"], "country": entry["country"], "reason": entry["reason"]}
    return [Signal(code="WL_NO_MATCH", engine="watchlist", severity="info",
                   message=f"No watchlist entry above {REVIEW_THRESHOLD}% similarity "
                           f"(closest: {matched_name!r} at {score:.0f}%).",
                   plain="This name does not resemble anyone on a sanctions or "
                         "watch list.", evidence=ev)]
