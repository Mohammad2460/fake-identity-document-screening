"""ICAO Doc 9303 machine-readable zone parsing and validation."""
from app.models import Signal

FILLER = "<"

def _char_value(c: str) -> int:
    if c == FILLER:
        return 0
    if c.isdigit():
        return int(c)
    if "A" <= c <= "Z":
        return ord(c) - 55
    raise ValueError(f"invalid MRZ character {c!r}")

def check_digit(s: str) -> int:
    weights = (7, 3, 1)
    return sum(_char_value(c) * weights[i % 3] for i, c in enumerate(s)) % 10

def _names(line1: str) -> tuple[str, str]:
    body = line1[5:]
    surname, _, given = body.partition("<<")
    clean = lambda x: " ".join(p for p in x.split(FILLER) if p)
    return clean(surname), clean(given)

def parse_td3(line1: str, line2: str) -> dict:
    surname, given = _names(line1)
    return {
        "country": line1[2:5].replace(FILLER, ""),
        "surname": surname,
        "given_names": given,
        "doc_number_raw": line2[0:9],
        "dob_raw": line2[13:19],
        "expiry_raw": line2[21:27],
        "doc_number": line2[0:9].replace(FILLER, ""),
        "doc_number_cd": line2[9],
        "nationality": line2[10:13].replace(FILLER, ""),
        "dob": line2[13:19],
        "dob_cd": line2[19],
        "sex": line2[20],
        "expiry": line2[21:27],
        "expiry_cd": line2[27],
        "personal_number": line2[28:42],
        "personal_number_cd": line2[42],
        "final_cd": line2[43],
    }

_FIELD_CHECKS = [
    ("doc_number_raw", "doc_number_cd", "MRZ_DOCNUM_CHECKSUM_FAIL", "document number"),
    ("dob_raw", "dob_cd", "MRZ_DOB_CHECKSUM_FAIL", "date of birth"),
    ("expiry_raw", "expiry_cd", "MRZ_EXPIRY_CHECKSUM_FAIL", "expiry date"),
]

def run(mrz_lines: list[str], claimed: dict) -> list[Signal]:
    signals: list[Signal] = []

    if len(mrz_lines) < 2 or len(mrz_lines[0]) < 44 or len(mrz_lines[1]) < 44:
        return [Signal(
            code="MRZ_MALFORMED", engine="mrz", severity="medium",
            message="Machine-readable zone is missing or not a valid 2x44 TD3 block.",
            evidence={"lines": mrz_lines},
        )]

    try:
        f = parse_td3(mrz_lines[0], mrz_lines[1])
    except ValueError as e:
        return [Signal(code="MRZ_MALFORMED", engine="mrz", severity="medium",
                       message=f"MRZ contains invalid characters: {e}")]

    for raw_key, cd_key, code, label in _FIELD_CHECKS:
        raw = f[raw_key]
        expected = check_digit(raw)
        actual = f[cd_key]
        if not actual.isdigit() or int(actual) != expected:
            signals.append(Signal(
                code=code, engine="mrz", severity="high",
                message=(f"MRZ {label} check digit is {actual}, but the printed value "
                         f"{raw!r} computes to {expected}. Field was altered."),
                evidence={"field": raw, "expected": expected, "found": actual},
            ))

    claimed_name = (claimed.get("full_name") or "").strip().upper()
    if claimed_name:
        mrz_name = f"{f['given_names']} {f['surname']}".strip()
        if set(claimed_name.split()) != set(mrz_name.split()):
            signals.append(Signal(
                code="MRZ_NAME_MISMATCH", engine="mrz", severity="high",
                message=(f"Claimed name {claimed_name!r} does not match the name "
                         f"encoded in the MRZ ({mrz_name!r})."),
                evidence={"claimed": claimed_name, "mrz": mrz_name},
            ))

    if not signals:
        signals.append(Signal(
            code="MRZ_ALL_CHECKS_PASS", engine="mrz", severity="info",
            message="All MRZ check digits are valid and the name matches the claim.",
            evidence={"doc_number": f["doc_number"], "nationality": f["nationality"]},
        ))
    return signals
