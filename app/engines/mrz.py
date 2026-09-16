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

TD3_LEN = 44

# OCR reads MRZ glyphs without knowing which ICAO field it is in, so letter/digit
# look-alikes get swapped (measured on the rendered genuine sample: nationality
# "UTO" read as "UT0"). The field TYPE is fixed by ICAO 9303, so each position is
# repaired only towards the character class it must hold. Alphanumeric fields
# (document number, personal number) are never touched - there the ambiguity is
# real and the check digit must decide.
_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"})
_TO_DIGIT = str.maketrans({"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1",
                           "Z": "2", "S": "5", "G": "6", "B": "8"})
# TD3 line-2 spans: (start, end, "alpha" | "digit"); digit positions include check digits.
_LINE2_TYPES = [(9, 10, "digit"), (10, 13, "alpha"), (13, 20, "digit"), (20, 21, "alpha"),
                (21, 28, "digit"), (42, 44, "digit")]


def _clean(line: str) -> str:
    return (line or "").strip().upper().replace(" ", "").replace("«", "<<")


def normalise_td3(lines: list[str], is_visa: bool = False) -> list[str]:
    """Repair what OCR does to a genuine TD3 MRZ, without inventing content.

    - Line 1: OCR drops the run of trailing '<' fillers (rendered sample: 28 of 44
      characters returned). A line 1 that still ENDS in a filler is padded to 44;
      one cut mid-name is left short so it stays MRZ_MALFORMED.
    - Both lines: letter/digit look-alikes repaired by ICAO field type.
    Line 2 is never padded: it carries check digits, and padding would forge them.
    """
    out = [_clean(ln) for ln in lines]
    if len(out) < 2:
        return out
    l1, l2 = out[0], out[1]
    if len(l1) < TD3_LEN and l1.endswith(FILLER):
        l1 = l1.ljust(TD3_LEN, FILLER)
    if len(l1) >= 5:   # issuing state and names are letters-only
        l1 = l1[:2] + l1[2:].translate(_TO_ALPHA)
    # Personal-number field (positions 28-41) is free-form filler on a genuine
    # document; OCR drops its trailing '<' run the same way it does line 1's.
    # Pad it back up to its own 14-char width, but never invent the personal
    # or composite check digits (positions 42-43) that follow it - see F1.
    if 28 <= len(l2) < 42:
        l2 = l2.ljust(42, FILLER)
    # ICAO 9303 Part 7: on an MRV (visa), line-2 positions 28-43 are alphanumeric
    # optional data with no personal/composite check digits, so digit coercion
    # there corrupts the passport number a visa carries in that field - see R4.
    line2_types = [t for t in _LINE2_TYPES if not (is_visa and t[0] >= 28)]
    if len(l2) >= TD3_LEN:
        chars = list(l2)
        for start, end, kind in line2_types:
            table = _TO_ALPHA if kind == "alpha" else _TO_DIGIT
            chars[start:end] = list("".join(chars[start:end]).translate(table))
        l2 = "".join(chars)
    elif len(l2) >= 21:   # digit fields before the personal number can still be repaired
        chars = list(l2)
        for start, end, kind in line2_types:
            if end > len(chars):
                break
            table = _TO_ALPHA if kind == "alpha" else _TO_DIGIT
            chars[start:end] = list("".join(chars[start:end]).translate(table))
        l2 = "".join(chars)
    return [l1, l2] + out[2:]


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

def name_tokens(name: str) -> list[str]:
    normalised = (name or "").upper()
    for ch in ("-", "'", FILLER):
        normalised = normalised.replace(ch, " ")
    return [t for t in normalised.split() if t]

def names_match(claimed_tokens: list[str], mrz_tokens: list[str]) -> bool:
    def is_match(mrz_tok: str, claimed_tok: str) -> bool:
        return mrz_tok == claimed_tok or claimed_tok.startswith(mrz_tok)

    mrz_ok = all(any(is_match(m, c) for c in claimed_tokens) for m in mrz_tokens)
    claimed_ok = all(
        any(is_match(m, c) for m in mrz_tokens) for c in claimed_tokens if len(c) >= 2
    )
    return mrz_ok and claimed_ok

_FIELD_CHECKS = [
    ("doc_number_raw", "doc_number_cd", "MRZ_DOCNUM_CHECKSUM_FAIL", "document number"),
    ("dob_raw", "dob_cd", "MRZ_DOB_CHECKSUM_FAIL", "date of birth"),
    ("expiry_raw", "expiry_cd", "MRZ_EXPIRY_CHECKSUM_FAIL", "expiry date"),
]

def run(mrz_lines: list[str], claimed: dict) -> list[Signal]:
    signals: list[Signal] = []

    mrz_lines = normalise_td3(mrz_lines)

    # Line 2 is readable enough to judge once the personal-number field (through
    # position 42) is present; the last 1-2 characters (personal check digit,
    # composite check digit) are the only ones OCR may still be missing, and
    # normalise_td3 pads the personal-number field itself but never invents a
    # check digit. See F1.
    if len(mrz_lines) < 2 or len(mrz_lines[0]) < TD3_LEN or len(mrz_lines[1]) < 42:
        return [Signal(
            code="MRZ_MALFORMED", engine="mrz", severity="medium",
            message="Machine-readable zone is missing or not a valid 2x44 TD3 block.",
            evidence={"lines": mrz_lines},
        )]

    l1 = mrz_lines[0]
    l2_raw = mrz_lines[1]
    tail_missing = TD3_LEN - len(l2_raw)   # 0, 1 or 2 trailing characters OCR did not read
    l2 = l2_raw.ljust(TD3_LEN, FILLER)

    try:
        f = parse_td3(l1, l2)

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

        if tail_missing < 2:   # the personal check digit (position 42) was read
            personal_number = f["personal_number"]
            personal_cd = f["personal_number_cd"]
            if not (personal_cd == FILLER and set(personal_number) <= {FILLER}):
                expected_personal = check_digit(f["personal_number"])
                if not personal_cd.isdigit() or int(personal_cd) != expected_personal:
                    signals.append(Signal(
                        code="MRZ_PERSONAL_CHECKSUM_FAIL", engine="mrz", severity="high",
                        message=(f"MRZ personal number check digit is {personal_cd}, but the "
                                 f"printed value {f['personal_number']!r} computes to "
                                 f"{expected_personal}. Field was altered."),
                        evidence={"field": f["personal_number"], "expected": expected_personal,
                                  "found": personal_cd},
                    ))

        if tail_missing < 1:   # the composite check digit (position 43) was read
            composite_input = l2[0:10] + l2[13:20] + l2[21:43]
            expected_composite = check_digit(composite_input)
            actual_composite = f["final_cd"]
            if not actual_composite.isdigit() or int(actual_composite) != expected_composite:
                signals.append(Signal(
                    code="MRZ_COMPOSITE_CHECKSUM_FAIL", engine="mrz", severity="high",
                    message=(f"MRZ composite check digit is {actual_composite}, but the "
                             f"fields it protects compute to {expected_composite}. The composite "
                             f"digit protects the whole line, so a field and its own check "
                             f"digit were changed together."),
                    evidence={"expected": expected_composite, "found": actual_composite},
                ))

        if tail_missing > 0:
            signals.append(Signal(
                code="MRZ_TAIL_UNREAD", engine="mrz", severity="low",
                message=(f"The last {tail_missing} character(s) of the MRZ second line were "
                         f"not read by OCR, so the personal-number and/or composite check "
                         f"digit could not be verified. This is an OCR read limitation, not "
                         f"evidence of tampering."),
                evidence={"chars_missing": tail_missing}))
    except ValueError as e:
        return [Signal(code="MRZ_MALFORMED", engine="mrz", severity="medium",
                       message=f"MRZ contains invalid characters: {e}")]

    claimed_name = (claimed.get("full_name") or "").strip().upper()
    if claimed_name:
        mrz_name = f"{f['given_names']} {f['surname']}".strip()
        claimed_tokens = name_tokens(claimed_name)
        mrz_tokens = name_tokens(mrz_name)
        if not names_match(claimed_tokens, mrz_tokens):
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
