"""One-time fetch of synthetic portraits for the demo samples. Requires network; setup only.

Source: SFHQ dataset sample grid (github.com/SelfishGene/SFHQ-dataset, MIT licence,
Copyright (c) 2022 David Beniaguev). Every face is StyleGAN-generated: the people do
not exist. No other face source is permitted in this project.

Run from the repo root:  ./.venv/bin/python -m scripts.fetch_faces
"""
import os
import tempfile
import urllib.request
import numpy as np
from PIL import Image

GRID_URL = ("https://raw.githubusercontent.com/SelfishGene/SFHQ-dataset/main/"
            "images/SFHQ_sample_2x4.jpg")
ROWS, COLS = 2, 4
OUT = "data/faces"
SIZE = 320
GUTTER_STD = 8.0     # a row/column of the grid this flat is gutter, not picture


def _runs(content: np.ndarray) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, on in enumerate(content):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(content)))
    return runs


def _longest(runs: list[tuple[int, int]], n: int) -> list[tuple[int, int]]:
    return sorted(sorted(runs, key=lambda r: r[1] - r[0], reverse=True)[:n])


def grid_cells(img: Image.Image, rows: int = ROWS, cols: int = COLS) -> list[tuple]:
    """(x0, y0, x1, y1) of each picture cell, row by row, measured from the gutters.

    Gutters are near-constant dark lines; the caption strips above each row are
    short runs, so the `rows` longest vertical runs are the pictures."""
    gray = np.asarray(img.convert("L"), dtype=np.float64)
    xs = _longest(_runs(gray.std(axis=0) >= GUTTER_STD), cols)
    ys = _longest(_runs(gray.std(axis=1) >= GUTTER_STD), rows)
    return [(x0, y0, x1, y1) for (y0, y1) in ys for (x0, x1) in xs]


LICENSE_TEXT = """Portrait crops in this directory: SFHQ dataset sample grid
Source: {url}
Project: https://github.com/SelfishGene/SFHQ-dataset

These are SYNTHETIC faces of NON-EXISTENT people (StyleGAN2 generated). They are used
only as portraits on synthetic demo documents. No real person is depicted.

MIT License

Copyright (c) 2022 David Beniaguev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def _download(url: str, dest: str) -> None:
    # python.org macOS builds ship without a CA bundle; use certifi's when present.
    ctx = None
    try:
        import ssl
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    with urllib.request.urlopen(url, context=ctx, timeout=60) as resp, open(dest, "wb") as fh:
        fh.write(resp.read())


def main() -> None:
    from app.engines import face
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="sfhq_")
    grid_path = os.path.join(work, "grid.jpg")
    part = grid_path + ".part"
    print(f"[get ] {GRID_URL}")
    try:
        _download(GRID_URL, part)
        os.replace(part, grid_path)
    except Exception:
        if os.path.exists(part):
            os.remove(part)
        raise

    with Image.open(grid_path) as im:
        grid = im.convert("RGB")
    kept = 0
    for i, (x0, y0, x1, y1) in enumerate(grid_cells(grid)):
        side = min(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        crop = grid.crop((cx - side // 2, cy - side // 2,
                          cx - side // 2 + side, cy - side // 2 + side))
        dest = os.path.join(OUT, f"sfhq_{i:02d}.jpg")
        tmp = os.path.join(work, f"sfhq_{i:02d}.jpg")
        crop.resize((SIZE, SIZE), Image.LANCZOS).save(tmp, "JPEG", quality=92)
        n = len(face.detect_faces(tmp))
        if n != 1:
            print(f"[drop] cell {i}: {n} faces detected")
            continue
        os.replace(tmp, dest)
        kept += 1
        print(f"[ok  ] {dest}")
    with open(os.path.join(OUT, "LICENSE-SFHQ.txt"), "w") as fh:
        fh.write(LICENSE_TEXT.format(url=GRID_URL))
    os.remove(grid_path)
    os.rmdir(work) if not os.listdir(work) else None
    print(f"Kept {kept} synthetic faces in {OUT}/")


if __name__ == "__main__":
    main()
