"""Generates synthetic clean and forged passports and visas for the SIH26188 demo."""
import io
import json
import os
import random
from PIL import Image, ImageDraw, ImageFont, ImageOps
from app.engines.mrz import check_digit

OUT = "data/samples"
W, H = 1000, 640

def _font(size: int):
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def _mono(size: int):
    for path in ("/System/Library/Fonts/Menlo.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                 "C:/Windows/Fonts/consola.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def build_mrz(doc_type: str, surname: str, given: str, doc_no: str, nat: str,
              dob: str, sex: str, expiry: str, personal: str = "") -> tuple[str, str]:
    name_field = f"{surname}<<{given.replace(' ', '<')}".ljust(39, "<")[:39]
    l1 = f"{doc_type}<{nat}{name_field}"
    doc = doc_no.ljust(9, "<")[:9]
    # R2: the personal-number / optional-data field (TD3 line 2 chars 28-41). On a
    # visa this carries the passport number the visa was issued against.
    personal = personal.ljust(14, "<")[:14] if personal else "<" * 14
    body = (f"{doc}{check_digit(doc)}{nat}{dob}{check_digit(dob)}{sex}"
            f"{expiry}{check_digit(expiry)}{personal}{check_digit(personal)}")
    composite = (doc + str(check_digit(doc)) + dob + str(check_digit(dob)) +
                 expiry + str(check_digit(expiry)) + personal + str(check_digit(personal)))
    return l1, (body + str(check_digit(composite))).ljust(44, "<")[:44]

def _noise(img: Image.Image, seed: int = 7) -> None:
    px = img.load()
    rng = random.Random(seed)
    for _ in range(img.width * img.height // 10):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        r, g, b = px[x, y]
        j = rng.randint(-8, 8)
        px[x, y] = (max(0, min(255, r + j)), max(0, min(255, g + j)), max(0, min(255, b + j)))

# Field layout shared by drawing and tampering, so a retyped field lands exactly in place.
FIELD_X, FIELD_Y0, FIELD_STEP = 300, 120, 58
FIELDS = ["Surname", "Given names", "Passport No.", "Nationality",
          "Date of birth", "Sex", "Date of expiry"]

def field_value_box(index: int) -> tuple[int, int, int, int]:
    y = FIELD_Y0 + index * FIELD_STEP + 18
    return FIELD_X - 4, y - 2, 420, 34

# Portraits are synthetic faces of NON-EXISTENT people: SFHQ dataset crops (MIT licence,
# see data/faces/LICENSE-SFHQ.txt), fetched once by scripts/fetch_faces.py.
FACES_DIR = "data/faces"
FACE_A = "sfhq_01.jpg"   # the genuine holder, Anna Maria Eriksson
FACE_B = "sfhq_02.jpg"   # a different (also non-existent) person - the substituted photo
PORTRAIT_BOX = (50, 120, 250, 380)   # x0, y0, x1, y1

def face_path(face_file: str) -> str:
    """A bare file name lives in data/faces; anything else is used as given, so
    scripts.make_demo_passport can pass a photo from outside the repo."""
    return face_file if os.path.sep in face_file else os.path.join(FACES_DIR, face_file)

def _portrait_image(face_file: str) -> Image.Image:
    """The face cropped to the portrait box's aspect, resized, slightly desaturated."""
    x0, y0, x1, y1 = PORTRAIT_BOX
    bw, bh = x1 - x0, y1 - y0
    with Image.open(face_path(face_file)) as im:
        src = im.convert("RGB")
    sw, sh = src.size
    if sw / sh > bw / bh:             # too wide: trim the sides
        cw = round(sh * bw / bh)
        src = src.crop(((sw - cw) // 2, 0, (sw - cw) // 2 + cw, sh))
    else:                             # too tall: trim top and bottom
        ch = round(sw * bh / bw)
        src = src.crop((0, (sh - ch) // 2, sw, (sh - ch) // 2 + ch))
    src = src.resize((bw, bh), Image.LANCZOS)
    grey = ImageOps.grayscale(src).convert("RGB")
    return Image.blend(src, grey, 0.2)

def paste_portrait(img: Image.Image, face_file: str = FACE_A) -> Image.Image:
    """Put a photograph into the portrait box - as issued, or as a forger would.
    Without data/faces (fetch not run) the box stays a flat grey placeholder."""
    if not os.path.exists(face_path(face_file)):
        ImageDraw.Draw(img).rectangle(PORTRAIT_BOX, fill=(205, 205, 200))
        return img
    img.paste(_portrait_image(face_file), PORTRAIT_BOX[:2])
    return img

def draw_passport(p: dict, mrz_override=None, face_file: str = FACE_A) -> Image.Image:
    img = Image.new("RGB", (W, H), (236, 234, 224))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 80], fill=(22, 52, 96))
    d.text((28, 22), "REPUBLIC OF UTOPIA   ·   PASSPORT", font=_font(30), fill="white")
    values = [p["surname"], p["given"], p["doc_no"], p["nat"],
              f"{p['dob'][4:6]}/{p['dob'][2:4]}/19{p['dob'][0:2]}", p["sex"],
              f"{p['expiry'][4:6]}/{p['expiry'][2:4]}/20{p['expiry'][0:2]}"]
    for i, (label, value) in enumerate(zip(FIELDS, values)):
        y = FIELD_Y0 + i * FIELD_STEP
        d.text((FIELD_X, y), label.upper(), font=_font(14), fill=(110, 110, 110))
        d.text((FIELD_X, y + 18), str(value), font=_font(26), fill=(15, 15, 15))
    paste_portrait(img, face_file)
    l1, l2 = mrz_override or build_mrz("P", p["surname"], p["given"], p["doc_no"],
                                       p["nat"], p["dob"], p["sex"], p["expiry"])
    d.rectangle([0, H - 110, W, H], fill=(250, 250, 246))
    d.text((28, H - 94), l1, font=_mono(24), fill=(10, 10, 10))
    d.text((28, H - 52), l2, font=_mono(24), fill=(10, 10, 10))
    _noise(img)
    return img

def draw_visa(p: dict, *, visa_passport_no: str | None = None,
              visa_no: str = "V10293847", stamp: bool = True) -> Image.Image:
    img = Image.new("RGB", (W, H), (242, 238, 226))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 80], fill=(96, 30, 44))
    d.text((28, 22), "REPUBLIC OF UTOPIA   ·   ENTRY VISA", font=_font(30), fill="white")
    # The passport this visa was issued against (printed, and carried in the MRZ
    # personal-number field) - NOT the visa's own document number (R2 / ICAO 9303
    # Part 7: an MRV's own line-2 document number is the visa's number).
    issued_against = visa_passport_no or p["doc_no"]
    rows = [("Holder", f"{p['given']} {p['surname']}"), ("Passport No.", issued_against),
            ("Nationality", p["nat"]), ("Visa type", "TOURIST - SINGLE ENTRY"),
            ("Valid until", "31/12/2030")]
    for i, (label, value) in enumerate(rows):
        y = FIELD_Y0 + i * 64
        d.text((FIELD_X, y), label.upper(), font=_font(14), fill=(110, 110, 110))
        d.text((FIELD_X, y + 18), value, font=_font(26), fill=(15, 15, 15))
    paste_portrait(img)
    if stamp:
        d.ellipse([720, 330, 930, 470], outline=(30, 60, 170), width=6)
        d.text((752, 382), "ENTRY  2026", font=_font(26), fill=(30, 60, 170))
    l1, l2 = build_mrz("V", p["surname"], p["given"], visa_no, p["nat"],
                       p["dob"], p["sex"], p["expiry"], personal=issued_against)
    d.rectangle([0, H - 110, W, H], fill=(250, 250, 246))
    d.text((28, H - 94), l1, font=_mono(24), fill=(10, 10, 10))
    d.text((28, H - 52), l2, font=_mono(24), fill=(10, 10, 10))
    _noise(img, seed=11)
    return img

def save_issued(img: Image.Image, path: str, quality: int = 70) -> None:
    """The genuine document's compression history."""
    img.save(path, "JPEG", quality=quality)

def reload(path: str) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGB").copy()

def retype_field(img: Image.Image, index: int, new_value: str) -> Image.Image:
    """What a forger does in an image editor: paint over a field, type a new value."""
    d = ImageDraw.Draw(img)
    x, y, w, h = field_value_box(index)
    d.rectangle([x, y, x + w, y + h], fill=(236, 234, 224))
    d.text((FIELD_X, y + 2), new_value, font=_font(26), fill=(15, 15, 15))
    return img

BASE = dict(surname="ERIKSSON", given="ANNA MARIA", doc_no="L898902C3",
            nat="UTO", dob="740812", sex="F", expiry="301231")
ANNA = {"full_name": "Anna Maria Eriksson", "dob": "1974-08-12",
        "passport_no": "L898902C3", "nationality": "UTO",
        "email": "anna.eriksson@gmail.com", "phone": "9845012763"}

def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    m = []

    # 1. Genuine passport
    save_issued(draw_passport(BASE), f"{OUT}/01_clean_passport.jpg")
    m.append({"files": {"document": "01_clean_passport.jpg"}, "claimed": ANNA,
              "expect": "CLEAR", "attack": "none",
              "story": "Genuine passport, applicant details match."})

    # 2. MRZ digit altered - the check digit no longer agrees
    l1, l2 = build_mrz("P", **{k: BASE[k] for k in ("surname", "given", "doc_no",
                                                     "nat", "dob", "sex", "expiry")})
    bad = l2[:3] + ("9" if l2[3] != "9" else "7") + l2[4:]
    save_issued(draw_passport(BASE, mrz_override=(l1, bad)), f"{OUT}/02_mrz_tampered.jpg")
    m.append({"files": {"document": "02_mrz_tampered.jpg"}, "claimed": ANNA,
              "expect": "REVIEW/REJECT", "attack": "altered passport number",
              "story": "One digit of the passport number changed. ICAO check digit fails."})

    # 3. DOB retyped - the centerpiece case
    path = f"{OUT}/03_dob_retyped.jpg"
    save_issued(draw_passport(BASE), path)
    retype_field(reload(path), FIELDS.index("Date of birth"), "12/08/1994") \
        .save(path, "JPEG", quality=97)
    m.append({"files": {"document": "03_dob_retyped.jpg"},
              "claimed": dict(ANNA, dob="1994-08-12"),
              "expect": "REVIEW", "attack": "altered DOB",
              "story": "Applicant made themself 20 years younger. The DOB field has a "
                       "different compression history from every other field - boxed red. "
                       "The MRZ still encodes the true 1974 DOB."})

    # 4. Photograph substituted
    path = f"{OUT}/04_photo_substituted.jpg"
    save_issued(draw_passport(BASE), path)
    paste_portrait(reload(path), FACE_B).save(path, "JPEG", quality=97)
    m.append({"files": {"document": "04_photo_substituted.jpg"}, "claimed": ANNA,
              "expect": "REVIEW", "attack": "altered photograph",
              "story": "Portrait replaced after issue with a photo of a different person. "
                       "The photo region is a compression outlier - boxed red."})

    # 5. Name retyped
    path = f"{OUT}/05_name_retyped.jpg"
    save_issued(draw_passport(BASE), path)
    retype_field(reload(path), FIELDS.index("Surname"), "SHARMA") \
        .save(path, "JPEG", quality=97)
    m.append({"files": {"document": "05_name_retyped.jpg"},
              "claimed": dict(ANNA, full_name="Anna Maria Sharma"),
              "expect": "REVIEW/REJECT", "attack": "altered name",
              "story": "Surname retyped. Field boxed red, and the MRZ still says ERIKSSON."})

    # 6. Visa with forged stamp
    path = f"{OUT}/06_visa_forged_stamp.jpg"
    save_issued(draw_visa(BASE, stamp=False), path)
    img = reload(path)
    d = ImageDraw.Draw(img)
    d.ellipse([720, 330, 930, 470], outline=(30, 60, 170), width=6)
    d.text((752, 382), "ENTRY  2026", font=_font(26), fill=(30, 60, 170))
    img.save(path, "JPEG", quality=97)
    save_issued(draw_passport(BASE), f"{OUT}/06_passport_for_visa.jpg")
    m.append({"files": {"document": "06_passport_for_visa.jpg",
                        "visa": "06_visa_forged_stamp.jpg"},
              "claimed": ANNA, "expect": "REVIEW", "attack": "forged visa stamp",
              "story": "Entry stamp added to the visa after issue. Stamp region boxed red."})

    # 7. Visa issued against a different passport. The visa carries its OWN MRV
    # document number; the passport it was issued against (X47281956) travels in
    # the personal-number field and the printed "Passport No." row (R2).
    save_issued(draw_visa(BASE, visa_passport_no="X47281956"), f"{OUT}/07_visa_mismatch.jpg")
    m.append({"files": {"document": "01_clean_passport.jpg",
                        "visa": "07_visa_mismatch.jpg"},
              "claimed": ANNA, "expect": "REJECT", "attack": "cross-document mismatch",
              "story": "Both documents are individually flawless. The visa was issued "
                       "against passport X47281956; the passport presented is L898902C3."})

    with open(f"{OUT}/manifest.json", "w") as fh:
        json.dump(m, fh, indent=2)
    print(f"Wrote {len(m)} cases to {OUT}/")

if __name__ == "__main__":
    main()
