"""Builds the whole stage-demo document set around one consenting person's photo.

On stage a teammate stands in front of the laptop, these documents are
uploaded, and the webcam takes the selfie, so the face engine matches live. The
documents themselves are entirely invented - REPUBLIC OF UTOPIA, a made-up
number and date of birth, valid ICAO check digits - and carry a diagonal
"SPECIMEN - NOT A REAL DOCUMENT" watermark. Only the portrait is a real person.

One genuine pair, and one forgery per attack the problem statement names, each
caught by a different engine:

    demo_passport.jpg                genuine                     -> CLEAR
    demo_visa.jpg                    genuine, same passport      -> CLEAR
    demo_passport_dob_altered.jpg    DOB retyped                 -> fieldforensics
    demo_passport_name_altered.jpg   surname retyped             -> fieldforensics + mrz
    demo_passport_mrz_altered.jpg    one MRZ digit changed       -> mrz check digit
    demo_visa_stamp_forged.jpg       entry stamp added at issue  -> fieldforensics
    demo_visa_wrong_passport.jpg     visa for another passport   -> crossdoc
    demo_passport_forged.jpg         photo swapped (--forge-photo) -> fieldforensics + face

    python -m scripts.make_demo_passport --consent \
        --photo path/to/teammate.jpg --name "RAHUL SHARMA"
    python -m scripts.make_demo_passport --consent \
        --photo path/to/teammate.jpg --forge-photo path/to/other.jpg \
        --name "RAHUL SHARMA" --out data/demo_rahul

demo_claimed.json holds what the officer types, keyed by document: the two
forgeries that change a printed field are screened against the forged value,
because that is what an officer reading the document would enter.

The photo stays on this machine. data/demo/ and data/demo_*/ are gitignored,
and nothing this script writes may ever be committed. Delete it after the
hackathon.
"""
import argparse
import hashlib
import json
import os
import sys

from PIL import Image, ImageDraw

from scripts.make_samples import (FIELDS, H, W, _font, build_mrz, draw_entry_stamp,
                                  draw_passport, draw_visa, paste_portrait,
                                  reload, retype_field, save_issued)

DEFAULT_OUT = "data/demo"

# Invented document details. Nothing here belongs to the person in the photo.
# doc_no is replaced per person by document_numbers(); the rest is shared.
DEMO_DOC = {"doc_no": "U2938471", "nat": "UTO", "dob": "920415",
            "sex": "M", "expiry": "330731"}

# The visa is issued against that passport and carries its own MRV number.
DEMO_VISA_NO = "V77341902"


def document_numbers(name: str) -> tuple[str, str]:
    """A passport and visa number unique to this name.

    Two people built from the same defaults would otherwise share a passport
    number, and the velocity engine would rightly report the second one as the
    same document presented under a new name - a finding about our own demo
    setup, not about the document on screen.
    """
    digits = str(int(hashlib.sha256(name.upper().encode()).hexdigest()[:8], 16))
    digits = digits.rjust(10, "0")[-10:]
    # The same widths as the hand-picked defaults these replaced (U2938471,
    # V77341902). Wider numbers mean longer unbroken digit runs in the MRZ,
    # which the OCR reads less reliably - measured: a 9-digit passport number
    # produced MRZ_TAIL_UNREAD instead of MRZ_ALL_CHECKS_PASS.
    return "U" + digits[:7], "V" + digits[2:]

# What the forger retypes over the real 15/04/1992 - six years younger.
FORGED_DOB_PRINTED = "15/04/1998"
FORGED_DOB_CLAIMED = "1998-04-15"

# The surname a forger paints over the real one. The MRZ still says the truth,
# so the substitute must never be the holder's own surname - pick the first
# candidate that differs from it.
FORGED_SURNAME_CANDIDATES = ("SHARMA", "VERMA", "IYER")


def forged_surname(surname: str) -> str:
    for candidate in FORGED_SURNAME_CANDIDATES:
        if candidate != surname.upper():
            return candidate
    raise AssertionError("unreachable: candidates are distinct")

# The passport some OTHER traveller's visa was issued against.
OTHER_PASSPORT_NO = "X47281956"

# The watermark lives in a band BELOW the portrait (which ends at y=380) and
# ABOVE the MRZ (which starts at y=H-110), so neither the face engine nor the
# MRZ reader loses anything. A test asserts both bounds.
WATERMARK_BAND = (390, 520)

# The visa's own safe band: below the portrait (ends y=380) and below the last
# printed row ("Valid until", drawn to y=426), above the MRZ (starts y=H-110),
# and left of the entry stamp (STAMP_BOX starts at x=720) so the stamp region
# stays a clean subject for field forensics. A test asserts all four.
VISA_WATERMARK_BAND = (435, 505)
VISA_WATERMARK_MAX_WIDTH = 620
VISA_WATERMARK_CENTER_X = 350
WATERMARK_TEXT = "SPECIMEN - NOT A REAL DOCUMENT"
WATERMARK_ANGLE = 6
WATERMARK_RGBA = (176, 38, 30, 70)

CONSENT_NOTICE = """\
Consent recorded. Before you continue, read this out loud:
  - the photo you pass in stays on this machine; this script uploads nothing;
  - data/demo/ is gitignored - never commit a real person's photograph;
  - delete data/demo/ and the source photo after the hackathon;
  - the document is a SPECIMEN. It is not, and must not be shown as, real."""


def _watermark_layer(band_height: int, max_width: int = W - 40) -> Image.Image:
    """The rotated, translucent SPECIMEN text, scaled to fit the band."""
    font = _font(38)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    left, top, right, bottom = probe.textbbox((0, 0), WATERMARK_TEXT, font=font)
    layer = Image.new("RGBA", (right - left + 24, bottom - top + 24), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((12 - left, 12 - top), WATERMARK_TEXT,
                               font=font, fill=WATERMARK_RGBA)
    layer = layer.rotate(WATERMARK_ANGLE, expand=True, resample=Image.BICUBIC)
    if layer.height > band_height:      # keep it inside the safe band
        scale = band_height / layer.height
        layer = layer.resize((max(1, round(layer.width * scale)), band_height),
                             Image.LANCZOS)
    if layer.width > max_width:
        scale = max_width / layer.width
        layer = layer.resize((max_width, max(1, round(layer.height * scale))),
                             Image.LANCZOS)
    return layer


def draw_watermark(img: Image.Image, band: tuple[int, int] = WATERMARK_BAND,
                   max_width: int = W - 40,
                   center_x: int | None = None) -> Image.Image:
    """Stamp the specimen watermark. Drawn BEFORE the issue-save, so the whole
    page keeps one compression history and field forensics stays honest."""
    top, bottom = band
    layer = _watermark_layer(bottom - top, max_width)
    cx = W // 2 if center_x is None else center_x
    x = cx - layer.width // 2
    y = top + (bottom - top - layer.height) // 2
    img.paste(layer, (x, y), layer)
    return img


def draw_visa_watermark(img: Image.Image) -> Image.Image:
    return draw_watermark(img, band=VISA_WATERMARK_BAND,
                          max_width=VISA_WATERMARK_MAX_WIDTH,
                          center_x=VISA_WATERMARK_CENTER_X)


def forge_entry_stamp(img: Image.Image) -> Image.Image:
    """What a forger does to a visa: draw an entry stamp onto an issued page.
    The stamp is the only region re-compressed, so it stands out from the rest."""
    draw_entry_stamp(ImageDraw.Draw(img))
    return img


def split_name(name: str) -> tuple[str, str]:
    """"RAHUL SHARMA" -> given "RAHUL", surname "SHARMA" (MRZ convention)."""
    parts = [p for p in name.upper().replace("-", " ").split() if p]
    if len(parts) < 2:
        raise ValueError("give a first name and a surname, e.g. \"RAHUL SHARMA\"")
    return " ".join(parts[:-1]), parts[-1]


def claimed_details(name: str, doc_no: str | None = None) -> dict:
    """What the officer types into the form for this demo passport."""
    given, surname = split_name(name)
    doc_no = doc_no or document_numbers(name)[0]
    pretty = " ".join(w.capitalize() for w in (given + " " + surname).split())
    handle = (given.split()[0] + "." + surname).lower()
    return {"full_name": pretty,
            "dob": "19{}-{}-{}".format(DEMO_DOC["dob"][0:2], DEMO_DOC["dob"][2:4],
                                       DEMO_DOC["dob"][4:6]),
            "passport_no": doc_no, "nationality": DEMO_DOC["nat"],
            # checkpoint-4 R11: @example.com (RFC 2606), never a plausibly real address.
            "email": handle + "@example.com", "phone": "9845012763"}


def build(photo: str, name: str, out_dir: str, forge_photo: str | None = None,
          sex: str | None = None) -> dict:
    """Write the full stage set: a genuine passport and visa for one consenting
    person, plus forgeries of each that look right to the eye and are caught by
    a different engine."""
    given, surname = split_name(name)
    doc_no, visa_no = document_numbers(name)
    person = dict(DEMO_DOC, surname=surname, given=given, doc_no=doc_no)
    if sex:
        person["sex"] = sex.upper()
    photo = os.path.abspath(photo)

    os.makedirs(out_dir, exist_ok=True)
    out = lambda n: os.path.join(out_dir, n)          # noqa: E731
    claimed = claimed_details(name, doc_no)

    # 1. The genuine passport.
    genuine = out("demo_passport.jpg")
    save_issued(draw_watermark(draw_passport(person, face_file=photo)), genuine)

    # 2. The genuine visa, issued against that passport, same face.
    visa = out("demo_visa.jpg")
    save_issued(draw_visa_watermark(
        draw_visa(person, visa_passport_no=person["doc_no"],
                  visa_no=visa_no, face_file=photo)), visa)

    # 3. Forgery A - the date of birth painted over and retyped. Only that field
    # was re-saved, so its compression history differs from every other field
    # while the MRZ still encodes the true 1992 date.
    dob_altered = out("demo_passport_dob_altered.jpg")
    save_issued(draw_watermark(draw_passport(person, face_file=photo)), dob_altered)
    retype_field(reload(dob_altered), FIELDS.index("Date of birth"),
                 FORGED_DOB_PRINTED).save(dob_altered, "JPEG", quality=97)

    # 4. Forgery B - the surname painted over and retyped. The field is a
    # compression outlier AND the MRZ still encodes the real surname, so two
    # independent engines disagree with the printed page.
    name_altered = out("demo_passport_name_altered.jpg")
    save_issued(draw_watermark(draw_passport(person, face_file=photo)), name_altered)
    fake_surname = forged_surname(surname)
    retype_field(reload(name_altered), FIELDS.index("Surname"),
                 fake_surname).save(name_altered, "JPEG", quality=97)

    # 5. Forgery C - one digit of the passport number changed in the MRZ. The
    # page is otherwise untouched; ICAO 9303 check-digit arithmetic catches it.
    l1, l2 = build_mrz("P", person["surname"], person["given"], person["doc_no"],
                       person["nat"], person["dob"], person["sex"], person["expiry"])
    bad = l2[:3] + ("9" if l2[3] != "9" else "7") + l2[4:]
    mrz_altered = out("demo_passport_mrz_altered.jpg")
    save_issued(draw_watermark(
        draw_passport(person, mrz_override=(l1, bad), face_file=photo)), mrz_altered)

    # 6. Forgery D - an entry stamp added to the visa after it was issued.
    visa_forged = out("demo_visa_stamp_forged.jpg")
    save_issued(draw_visa_watermark(
        draw_visa(person, visa_passport_no=person["doc_no"], visa_no=visa_no,
                  stamp=False, face_file=photo)), visa_forged)
    forge_entry_stamp(reload(visa_forged)).save(visa_forged, "JPEG", quality=97)

    # 7. Forgery E - a flawless visa that belongs to a different passport.
    # Nothing on either page is tampered; only the two together disagree.
    visa_wrong = out("demo_visa_wrong_passport.jpg")
    save_issued(draw_visa_watermark(
        draw_visa(person, visa_passport_no=OTHER_PASSPORT_NO, visa_no=visa_no,
                  face_file=photo)), visa_wrong)

    forged_surname_full = " ".join(
        claimed["full_name"].split()[:-1] + [fake_surname.capitalize()])
    written = {"genuine": genuine, "visa": visa, "dob_altered": dob_altered,
               "name_altered": name_altered, "mrz_altered": mrz_altered,
               "visa_stamp_forged": visa_forged, "visa_wrong_passport": visa_wrong,
               "forged": None, "claimed": claimed,
               "claimed_dob_altered": dict(claimed, dob=FORGED_DOB_CLAIMED),
               "claimed_name_altered": dict(claimed, full_name=forged_surname_full)}

    # 8. Forgery F (optional) - exactly what a forger does: paste another face
    # into the issued document and re-save.
    if forge_photo:
        forged = out("demo_passport_forged.jpg")
        paste_portrait(reload(genuine), os.path.abspath(forge_photo)) \
            .save(forged, "JPEG", quality=97)
        written["forged"] = forged

    with open(out("demo_claimed.json"), "w") as fh:
        json.dump({"genuine": written["claimed"],
                   "dob_altered": written["claimed_dob_altered"],
                   "name_altered": written["claimed_name_altered"]}, fh, indent=2)
    return written


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(
        prog="python -m scripts.make_demo_passport",
        description="Build a SPECIMEN demo passport around a consenting person's photo.")
    ap.add_argument("--photo", required=True, help="the consenting person's photo")
    ap.add_argument("--name", required=True, help='e.g. "RAHUL SHARMA"')
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory (gitignored)")
    ap.add_argument("--forge-photo", default=None,
                    help="a second person's photo; also writes the swapped-photo forgery")
    ap.add_argument("--sex", default=None, help="M, F or X for the MRZ (default M)")
    ap.add_argument("--consent", action="store_true",
                    help="required: the person in the photo agreed to this use")
    args = ap.parse_args(argv)

    if not args.consent:
        sys.exit("Refusing to run without --consent.\n"
                 "Only build this from a photo of someone who agreed, in person, "
                 "to their face being used in the demo. Re-run with --consent.")
    for label, path in (("--photo", args.photo), ("--forge-photo", args.forge_photo)):
        if path and not os.path.exists(path):
            sys.exit(f"{label}: no such file: {path}")
    try:
        written = build(args.photo, args.name, args.out,
                        forge_photo=args.forge_photo, sex=args.sex)
    except ValueError as err:
        sys.exit(str(err))

    print(CONSENT_NOTICE)
    print("\nWrote:")
    rows = [("genuine", "genuine passport - expect CLEAR"),
            ("visa", "genuine visa for the same passport - upload with it, expect CLEAR"),
            ("dob_altered", "date of birth retyped - expect the DOB field boxed red"),
            ("name_altered", "surname retyped - expect the field boxed red AND an MRZ name mismatch"),
            ("mrz_altered", "one MRZ digit changed - expect the check digit to fail"),
            ("visa_stamp_forged", "entry stamp added after issue - expect the stamp boxed red"),
            ("visa_wrong_passport",
             "flawless visa issued against another passport - upload with the genuine "
             "passport, expect a cross-document mismatch")]
    if written["forged"]:
        rows.append(("forged", "photograph swapped - expect the photo boxed red"))
    for key, note in rows:
        print("  " + written[key] + "   (" + note + ")")
    print("  " + os.path.join(args.out, "demo_claimed.json")
          + "   (what to type into the form)")
    print("\nType these details for every file except the DOB forgery:")
    for k, v in written["claimed"].items():
        print(f"    {k}: {v}")
    print("  For " + os.path.basename(written["dob_altered"])
          + " type dob: " + written["claimed_dob_altered"]["dob"])
    print("  For " + os.path.basename(written["name_altered"])
          + " type full_name: " + written["claimed_name_altered"]["full_name"])
    print("  (the officer types what the document shows them, forged or not)")
    print("\nOn stage: upload the genuine passport and visa, type the details "
          'above, press "Use camera", capture the live selfie, and screen. Then '
          "re-run with each forged file to show what was altered, boxed red.")
    print("Screen the genuine pair FIRST: five screenings inside ten minutes trip "
          "the velocity engine's bulk-submission rule, which would add an unrelated "
          "finding to every later case. Between rehearsals, delete cases.db.")
    print("\nDelete " + args.out + " and the source photo after the hackathon.")
    return written


if __name__ == "__main__":
    main()
