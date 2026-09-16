"""The SFHQ sample grid is cut into single-face crops along its dark gutters."""
import numpy as np
from PIL import Image
from scripts.fetch_faces import grid_cells


def _grid(rows=2, cols=4, cell=100, gutter=10, title=20):
    w = cols * cell + (cols + 1) * gutter
    h = rows * (cell + title) + (rows + 1) * gutter
    a = np.full((h, w, 3), 12, np.uint8)
    rng = np.random.default_rng(0)
    boxes = []
    for r in range(rows):
        for c in range(cols):
            x = gutter + c * (cell + gutter)
            y = gutter + r * (cell + title + gutter) + title
            a[y:y + cell, x:x + cell] = rng.integers(40, 220, (cell, cell, 3))
            boxes.append((x, y, x + cell, y + cell))
    return Image.fromarray(a), boxes


def test_grid_cells_finds_every_image_cell_and_skips_title_strips():
    img, boxes = _grid()
    cells = grid_cells(img, rows=2, cols=4)
    assert len(cells) == 8
    for got, want in zip(cells, boxes):
        assert all(abs(g - w) <= 3 for g, w in zip(got, want)), (got, want)


def test_the_work_directory_sits_beside_its_destination():
    """os.replace cannot move a file between drives. On Windows the system temp
    directory is routinely on C: while the checkout is on D:, which made
    scripts.fetch_faces fail with WinError 17 on a teammate's machine. Keeping
    the scratch directory inside the destination keeps the rename atomic and on
    one filesystem."""
    import os
    from scripts import fetch_faces
    work = fetch_faces._workdir()
    try:
        assert os.path.dirname(os.path.abspath(work)) == os.path.abspath(fetch_faces.OUT)
    finally:
        os.rmdir(work)


def test_a_leftover_work_directory_is_not_mistaken_for_a_face():
    """It lives inside data/faces, so it must not match the crop glob."""
    import glob, os
    from scripts import fetch_faces
    work = fetch_faces._workdir()
    try:
        assert work not in glob.glob(os.path.join(fetch_faces.OUT, "sfhq_*.jpg"))
    finally:
        os.rmdir(work)
