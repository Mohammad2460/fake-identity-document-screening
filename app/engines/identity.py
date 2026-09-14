"""Screens the claimed person for signs of a fabricated identity."""
import re
from datetime import date, datetime
from app.models import Signal

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "throwawaymail.com", "yopmail.com", "trashmail.com", "sharklasers.com",
    "getnada.com", "temp-mail.org", "fakeinbox.com", "dispostable.com",
}

_KEYBOARD_RUNS = ("qwerty", "asdf", "zxcv", "qazwsx", "hjkl", "wasd", "poiuy")
_PASSPORT_RE = re.compile(r"^[A-Z0-9<]{6,12}$")

def passport_number_plausible(num: str) -> bool:
    return bool(_PASSPORT_RE.match((num or "").strip().upper()))

def _looks_like_keyboard_mash(text: str) -> bool:
    t = re.sub(r"[^a-z]", "", (text or "").lower())
    return any(run in t for run in _KEYBOARD_RUNS)

def _is_sequential(digits: str) -> bool:
    if len(digits) < 6:
        return False
    # mod 10 so keypad order wraps: 1234567890 and 0987654321 both count as runs
    asc = all((int(digits[i + 1]) - int(digits[i])) % 10 == 1 for i in range(len(digits) - 1))
    desc = all((int(digits[i]) - int(digits[i + 1])) % 10 == 1 for i in range(len(digits) - 1))
    return asc or desc or len(set(digits)) == 1

def _parse_dob(dob: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(dob.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None

def run(claimed: dict) -> list[Signal]:
    s: list[Signal] = []
    name = (claimed.get("full_name") or "").strip()
    email = (claimed.get("email") or "").strip().lower()
    phone = re.sub(r"\D", "", claimed.get("phone") or "")
    passport_no = (claimed.get("passport_no") or "").strip()
    dob = (claimed.get("dob") or "").strip()

    if passport_no and not passport_number_plausible(passport_no):
        s.append(Signal(
            code="ID_PASSPORT_FORMAT_ODD", engine="identity", severity="medium",
            message=f"Passport number {passport_no!r} does not match the 6-12 "
                    f"alphanumeric structure used by ICAO travel documents.",
            evidence={"passport_no": passport_no},
        ))

    if email:
        domain = email.rpartition("@")[2]
        if domain in DISPOSABLE_DOMAINS:
            s.append(Signal(
                code="ID_DISPOSABLE_EMAIL", engine="identity", severity="high",
                message=f"Email uses known disposable provider {domain!r}.",
                evidence={"domain": domain},
            ))
        local = email.partition("@")[0]
        digits = sum(c.isdigit() for c in local)
        if name and len(local) >= 6:
            parts = [p.lower() for p in re.split(r"\s+", name) if len(p) > 2]
            if not any(p[:4] in local for p in parts) and digits >= 3:
                s.append(Signal(
                    code="ID_EMAIL_NAME_DIVERGENCE", engine="identity", severity="medium",
                    message=(f"Email local-part {local!r} shares nothing with the claimed "
                             f"name and is digit-heavy — typical of bulk-generated accounts."),
                    evidence={"local_part": local},
                ))

    if phone:
        if len(phone) < 10:
            s.append(Signal(code="ID_PHONE_TOO_SHORT", engine="identity", severity="medium",
                            message=f"Phone number has only {len(phone)} digits."))
        elif _is_sequential(phone):
            s.append(Signal(
                code="ID_PHONE_SEQUENTIAL", engine="identity", severity="high",
                message=f"Phone number {phone!r} is a sequential or repeated digit run.",
                evidence={"phone": phone},
            ))

    if name:
        if _looks_like_keyboard_mash(name):
            s.append(Signal(
                code="ID_NAME_SUSPICIOUS", engine="identity", severity="high",
                message=f"Name {name!r} contains a keyboard-run pattern, not a real name.",
                evidence={"name": name},
            ))
        elif len(name.split()) < 2:
            s.append(Signal(code="ID_NAME_SINGLE_TOKEN", engine="identity", severity="low",
                            message="Only one name token supplied; full legal name expected."))

    if dob:
        d = _parse_dob(dob)
        if d is None:
            s.append(Signal(code="ID_DOB_UNPARSEABLE", engine="identity", severity="medium",
                            message=f"Date of birth {dob!r} is not a recognised date format."))
        else:
            age = (date.today() - d).days / 365.25
            if age < 18 or age > 110:
                s.append(Signal(
                    code="ID_DOB_IMPLAUSIBLE", engine="identity", severity="high",
                    message=f"Date of birth implies an age of {age:.0f}, outside 18-110.",
                    evidence={"dob": dob, "age": round(age, 1)},
                ))
    return s
