"""Draws the annotated evidence image: suspect regions boxed in red."""
import os
import uuid
import cv2

RED = (0, 0, 220)
GREEN = (90, 170, 90)

FONT, SCALE, THICK = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2

def _label(r: dict) -> str:
    return f"ALTERED: {r.get('label', '')}"[:40]

def _hits(a: tuple, b: tuple) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

def tab_rect(r: dict, regions: list[dict], shape: tuple) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the red label tab: above the box, unless that would cover a
    neighbouring region (e.g. the field's own printed label) - then to its right,
    then to its left - falling back to above."""
    img_h, img_w = shape[:2]
    x, y, w, h = [int(v) for v in r["box"]]
    (tw, th), _ = cv2.getTextSize(_label(r), FONT, SCALE, THICK)
    tw, th = tw + 8, th + 10
    others = [tuple(int(v) for v in o["box"]) for o in regions if o is not r]
    above = (x, max(0, y - th - 4), tw, th)
    cy = max(0, y + h // 2 - th // 2)
    for cand in (above, (x + w + 6, cy, tw, th), (x - tw - 6, cy, tw, th)):
        cx0, cy0, cw, ch = cand
        inside = cx0 >= 0 and cy0 >= 0 and cx0 + cw <= img_w and cy0 + ch <= img_h
        if inside and not _hits(cand, (x, y, w, h)) and not any(_hits(cand, o) for o in others):
            return cand
    return above

def draw_evidence(path: str, regions: list[dict], out_dir: str) -> str | None:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return None
    os.makedirs(out_dir, exist_ok=True)

    for r in regions:
        x, y, w, h = [int(v) for v in r["box"]]
        suspect = bool(r.get("suspect"))
        colour = RED if suspect else GREEN
        cv2.rectangle(img, (x, y), (x + w, y + h), colour, 3 if suspect else 1)
        if suspect:
            tx, ty, tw, th = tab_rect(r, regions, img.shape)
            cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), RED, -1)
            cv2.putText(img, _label(r), (tx + 4, ty + th - 6), FONT,
                        SCALE, (255, 255, 255), THICK, cv2.LINE_AA)

    dest = os.path.join(out_dir, f"{uuid.uuid4().hex}.jpg")
    if not cv2.imwrite(dest, img):
        return None
    return dest
