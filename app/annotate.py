"""Draws the annotated evidence image: suspect regions boxed in red."""
import os
import uuid
import cv2

RED = (0, 0, 220)
GREEN = (90, 170, 90)

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
            label = f"ALTERED: {r.get('label', '')}"[:40]
            ty = max(18, y - 8)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(img, (x, ty - th - 6), (x + tw + 8, ty + 4), RED, -1)
            cv2.putText(img, label, (x + 4, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (255, 255, 255), 2, cv2.LINE_AA)

    dest = os.path.join(out_dir, f"{uuid.uuid4().hex}.jpg")
    cv2.imwrite(dest, img)
    return dest
