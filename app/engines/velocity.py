"""Cross-submission fraud patterns: identity reuse, duplicate docs, bursts."""
from app import db
from app.models import Signal

BURST_WINDOW_MINUTES = 10
BURST_THRESHOLD = 5

def run(claimed: dict, doc_hash: str | None, db_path: str) -> list[Signal]:
    signals: list[Signal] = []
    name = (claimed.get("full_name") or "").strip().lower()

    prior = db.find_prior(
        db_path,
        passport_no=claimed.get("passport_no"),
        email=claimed.get("email"),
        phone=claimed.get("phone"),
        doc_hash=doc_hash,
    )

    if doc_hash:
        dupes = [p for p in prior if p["doc_hash"] == doc_hash]
        if dupes:
            conflicting_dupes = [
                p for p in dupes
                if (p["full_name"] or "").strip() and (p["full_name"] or "").strip().lower() != name
            ]
            if conflicting_dupes:
                signals.append(Signal(
                    code="VEL_DUPLICATE_DOCUMENT", engine="velocity", severity="critical",
                    message=(f"This exact document image was already submitted in case "
                             f"{conflicting_dupes[0]['case_id']} under the name "
                             f"{conflicting_dupes[0]['full_name']!r}."),
                    evidence={"prior_case": conflicting_dupes[0]["case_id"]},
                ))
            else:
                signals.append(Signal(
                    code="VEL_RESUBMISSION", engine="velocity", severity="info",
                    message=(f"This exact document was already screened before for the "
                             f"same person, in case {dupes[0]['case_id']}."),
                    evidence={"prior_case": dupes[0]["case_id"]},
                ))

    if claimed.get("passport_no"):
        conflicting = {
            p["full_name"] for p in prior
            if p["passport_no"] == claimed["passport_no"] and p["full_name"]
            and p["full_name"].strip().lower() != name
        }
        if conflicting:
            signals.append(Signal(
                code="VEL_ID_REUSED_NEW_NAME", engine="velocity", severity="critical",
                message=(f"The same passport number has previously been submitted under "
                         f"{len(conflicting)} different name(s): "
                         f"{', '.join(sorted(conflicting))}."),
                evidence={"conflicting_names": sorted(conflicting)},
            ))

    if db.recent_count(db_path, BURST_WINDOW_MINUTES) >= BURST_THRESHOLD:
        signals.append(Signal(
            code="VEL_SUBMISSION_BURST", engine="velocity", severity="medium",
            message=(f"{db.recent_count(db_path, BURST_WINDOW_MINUTES)} applications "
                     f"received in the last {BURST_WINDOW_MINUTES} minutes — "
                     f"consistent with automated bulk submission."),
        ))

    if not signals:
        signals.append(Signal(code="VEL_NO_PRIOR_HISTORY", engine="velocity", severity="info",
                              message="No prior submission matches this identity or document."))
    return signals
