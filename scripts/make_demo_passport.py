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

from scripts.make_samples import (H, W, _font, draw_passport, paste_portrait,
                                  reload, save_issued)

DEFAULT_OUT = "data/demo"

# Invented document details. Nothing here belongs to the person in the photo.
DEMO_DOC = {"doc_no": "U2938471", "nat": "UTO", "dob": "920415",
            "sex": "M", "expiry": "330731"}

# The watermark lives in a band BELOW the portrait (which ends at y=380) and
# ABOVE the MRZ (which starts at y=H-110), so neither the face engine nor the
# MRZ reader loses anything. A test asserts both bounds.
WATERMARK_BAND = (390, 520)
WATERMARK_TEXT = "SPECIMEN - NOT A REAL DOCUMENT"
WATERMARK_ANGLE = 6
WATERMARK_RGBA = (176, 38, 30, 70)

CONSENT_NOTICE = """\
Consent recorded. Before you continue, read this out loud:
  - the photo you pass in stays on this machine; this script uploads nothing;
  - data/demo/ is gitignored - never commit a real person's photograph;
  - delete data/demo/ and the source photo after the hackathon;
  - the document is a SPECIMEN. It is not, and must not be shown as, real."""


def _watermark_layer(band_height: int) -> Image.Image:
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
    if layer.width > W - 40:
        scale = (W - 40) / layer.width
        layer = layer.resize((W - 40, max(1, round(layer.height * scale))),
                             Image.LANCZOS)
    return layer


def draw_watermark(img: Image.Image) -> Image.Image:
    """Stamp the specimen watermark. Drawn BEFORE the issue-save, so the whole
    page keeps one compression history and field forensics stays honest."""
    top, bottom = WATERMARK_BAND
    layer = _watermark_layer(bottom - top)
    x = (W - layer.width) // 2
    y = top + (bottom - top - layer.height) // 2
    img.paste(layer, (x, y), layer)
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
            "email": handle + "@gmail.com", "phone": "9845012763"}


def build(photo: str, name: str, out_dir: str, forge_photo: str | None = None,
          sex: str | None = None) -> dict:
    """Write the demo passport (and optionally its swapped-photo forgery)."""
    given, surname = split_name(name)
    person = dict(DEMO_DOC, surname=surname, given=given)
    if sex:
        person["sex"] = sex.upper()

    os.makedirs(out_dir, exist_ok=True)
    genuine = os.path.join(out_dir, "demo_passport.jpg")
    img = draw_passport(person, face_file=os.path.abspath(photo))
    save_issued(draw_watermark(img), genuine)

    written = {"genuine": genuine, "forged": None,
               "claimed": claimed_details(name)}

    if forge_photo:
        # Exactly what a forger does: paste another face into the issued
        # document and re-save. The photo region's compression history now
        # differs from the rest of the page -> FF_PHOTO_TAMPERED.
        forged = os.path.join(out_dir, "demo_passport_forged.jpg")
        paste_portrait(reload(genuine), os.path.abspath(forge_photo)) \
            .save(forged, "JPEG", quality=97)
        written["forged"] = forged

    with open(os.path.join(out_dir, "demo_claimed.json"), "w") as fh:
        json.dump(written["claimed"], fh, indent=2)
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
    print("  " + written["genuine"] + "   (genuine specimen - expect CLEAR)")
    if written["forged"]:
        print("  " + written["forged"] + "   (photo swapped - expect FF_PHOTO_TAMPERED)")
    print("  " + os.path.join(args.out, "demo_claimed.json")
          + "   (what to type into the form)")
    print("\nOn stage: upload the genuine specimen, type the details above, press "
          '"Use camera", capture the live selfie, and screen. Then swap in the '
          "forged file to show the photograph boxed red.")
    print("\nDelete " + args.out + " and the source photo after the hackathon.")
    return written


if __name__ == "__main__":
    main()
