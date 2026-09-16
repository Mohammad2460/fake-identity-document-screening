"""Builds the stage-demo SPECIMEN passport around a consenting person's photo.

On stage a teammate stands in front of the laptop, this passport is uploaded,
and the webcam takes the selfie, so the face engine matches live. The document
itself is entirely invented - REPUBLIC OF UTOPIA, a made-up number and date of
birth, valid ICAO check digits - and carries a diagonal
"SPECIMEN - NOT A REAL DOCUMENT" watermark. Only the portrait is a real person.

    python -m scripts.make_demo_passport --consent \
        --photo path/to/teammate.jpg --name "RAHUL SHARMA"
    python -m scripts.make_demo_passport --consent \
        --photo path/to/teammate.jpg --forge-photo path/to/other.jpg \
        --name "RAHUL SHARMA"

The photo stays on this machine. data/demo/ is gitignored, and nothing this
script writes may ever be committed. Delete it after the hackathon.
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw

from scripts.make_samples import (FIELDS, H, W, _font, build_mrz, draw_passport,
                                  draw_visa, paste_portrait, reload,
                                  retype_field, save_issued)

DEFAULT_OUT = "data/demo"

# Invented document details. Nothing here belongs to the person in the photo.
DEMO_DOC = {"doc_no": "U2938471", "nat": "UTO", "dob": "920415",
            "sex": "M", "expiry": "330731"}

# The visa is issued against that passport and carries its own MRV number.
DEMO_VISA_NO = "V77341902"

# What the forger retypes over the real 15/04/1992 - twenty-six years younger.
FORGED_DOB_PRINTED = "15/04/1998"
FORGED_DOB_CLAIMED = "1998-04-15"

# The watermark lives in a band BELOW the portrait (which ends at y=380) and
# ABOVE the MRZ (which starts at y=H-110), so neither the face engine nor the
# MRZ reader loses anything. A test asserts both bounds.
WATERMARK_BAND = (390, 520)

# The visa's own safe band: below the portrait (ends y=380), above the MRZ
# (starts y=H-110), and left of the entry stamp (starts x=720) so the stamp
# region stays a clean subject for field forensics. A test asserts all three.
VISA_WATERMARK_BAND = (400, 505)
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
    d = ImageDraw.Draw(img)
    d.ellipse([720, 330, 930, 470], outline=(30, 60, 170), width=6)
    d.text((752, 382), "ENTRY  2026", font=_font(26), fill=(30, 60, 170))
    return img


def split_name(name: str) -> tuple[str, str]:
    """"RAHUL SHARMA" -> given "RAHUL", surname "SHARMA" (MRZ convention)."""
    parts = [p for p in name.upper().replace("-", " ").split() if p]
    if len(parts) < 2:
        raise ValueError("give a first name and a surname, e.g. \"RAHUL SHARMA\"")
    return " ".join(parts[:-1]), parts[-1]


def claimed_details(name: str) -> dict:
    """What the officer types into the form for this demo passport."""
    given, surname = split_name(name)
    pretty = " ".join(w.capitalize() for w in (given + " " + surname).split())
    handle = (given.split()[0] + "." + surname).lower()
    return {"full_name": pretty,
            "dob": "19{}-{}-{}".format(DEMO_DOC["dob"][0:2], DEMO_DOC["dob"][2:4],
                                       DEMO_DOC["dob"][4:6]),
            "passport_no": DEMO_DOC["doc_no"], "nationality": DEMO_DOC["nat"],
            # checkpoint-4 R11: @example.com (RFC 2606), never a plausibly real address.
            "email": handle + "@example.com", "phone": "9845012763"}


def build(photo: str, name: str, out_dir: str, forge_photo: str | None = None,
          sex: str | None = None) -> dict:
    """Write the full stage set: a genuine passport and visa for one consenting
    person, plus forgeries of each that look right to the eye and are caught by
    a different engine."""
    given, surname = split_name(name)
    person = dict(DEMO_DOC, surname=surname, given=given)
    if sex:
        person["sex"] = sex.upper()
    photo = os.path.abspath(photo)

    os.makedirs(out_dir, exist_ok=True)
    out = lambda n: os.path.join(out_dir, n)          # noqa: E731
    claimed = claimed_details(name)

    # 1. The genuine passport.
    genuine = out("demo_passport.jpg")
    save_issued(draw_watermark(draw_passport(person, face_file=photo)), genuine)

    # 2. The genuine visa, issued against that passport, same face.
    visa = out("demo_visa.jpg")
    save_issued(draw_visa_watermark(
        draw_visa(person, visa_passport_no=person["doc_no"],
                  visa_no=DEMO_VISA_NO, face_file=photo)), visa)

    # 3. Forgery A - the date of birth painted over and retyped. Only that field
    # was re-saved, so its compression history differs from every other field
    # while the MRZ still encodes the true 1992 date.
    dob_altered = out("demo_passport_dob_altered.jpg")
    save_issued(draw_watermark(draw_passport(person, face_file=photo)), dob_altered)
    retype_field(reload(dob_altered), FIELDS.index("Date of birth"),
                 FORGED_DOB_PRINTED).save(dob_altered, "JPEG", quality=97)

    # 4. Forgery B - one digit of the passport number changed in the MRZ. The
    # page is otherwise untouched; ICAO 9303 check-digit arithmetic catches it.
    l1, l2 = build_mrz("P", person["surname"], person["given"], person["doc_no"],
                       person["nat"], person["dob"], person["sex"], person["expiry"])
    bad = l2[:3] + ("9" if l2[3] != "9" else "7") + l2[4:]
    mrz_altered = out("demo_passport_mrz_altered.jpg")
    save_issued(draw_watermark(
        draw_passport(person, mrz_override=(l1, bad), face_file=photo)), mrz_altered)

    # 5. Forgery C - an entry stamp added to the visa after it was issued.
    visa_forged = out("demo_visa_stamp_forged.jpg")
    save_issued(draw_visa_watermark(
        draw_visa(person, visa_passport_no=person["doc_no"], visa_no=DEMO_VISA_NO,
                  stamp=False, face_file=photo)), visa_forged)
    forge_entry_stamp(reload(visa_forged)).save(visa_forged, "JPEG", quality=97)

    written = {"genuine": genuine, "visa": visa, "dob_altered": dob_altered,
               "mrz_altered": mrz_altered, "visa_stamp_forged": visa_forged,
               "forged": None, "claimed": claimed,
               "claimed_dob_altered": dict(claimed, dob=FORGED_DOB_CLAIMED)}

    # 6. Forgery D (optional) - exactly what a forger does: paste another face
    # into the issued document and re-save.
    if forge_photo:
        forged = out("demo_passport_forged.jpg")
        paste_portrait(reload(genuine), os.path.abspath(forge_photo)) \
            .save(forged, "JPEG", quality=97)
        written["forged"] = forged

    with open(out("demo_claimed.json"), "w") as fh:
        json.dump({"genuine": written["claimed"],
                   "dob_altered": written["claimed_dob_altered"]}, fh, indent=2)
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
            ("mrz_altered", "one MRZ digit changed - expect the check digit to fail"),
            ("visa_stamp_forged", "entry stamp added after issue - expect the stamp boxed red")]
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
          + " type dob: " + written["claimed_dob_altered"]["dob"]
          + " instead - the officer is shown the forged date.")
    print("\nOn stage: upload the genuine passport and visa, type the details "
          'above, press "Use camera", capture the live selfie, and screen. Then '
          "re-run with each forged file to show what was altered, boxed red.")
    print("\nDelete " + args.out + " and the source photo after the hackathon.")
    return written


if __name__ == "__main__":
    main()
