"""Turn a text PDF into a scanned-looking, image-only PDF (nothing can be selected or copied).

Each page is drawn as a picture, then given the small flaws of a real scan: a slight tilt, off-white paper,
grain, soft edges and a faint shadow at the border. The output has no text layer.
Needs pdfplumber (which brings pypdfium2 to draw the pages), Pillow and numpy. No other program is needed. Run through `python -m seed.make_pdfs`, or alone:
    python -m seed.make_scan input.pdf output.pdf
"""
import io
import random
import sys

import numpy as np
import pdfplumber
from PIL import Image, ImageFilter


def _scan_page(img, rng):
    img = img.convert("L")
    w, h = img.size
    img = img.rotate(rng.uniform(-0.6, 0.6), resample=Image.BICUBIC, expand=False, fillcolor=255)
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    a = np.asarray(img, dtype=np.float32)
    a = 255 - (255 - a) * 0.88                                   # ink slightly faded, like toner
    yy, xx = np.mgrid[0:h, 0:w]
    edge = np.minimum.reduce([xx, w - 1 - xx, yy, h - 1 - yy]) / (0.04 * w)
    a *= 0.80 + 0.20 * np.clip(edge, 0, 1)                      # darker at the border
    a *= 0.97 + 0.03 * (yy / h)                                  # uneven lighting
    a += np.random.default_rng(rng.randrange(1 << 30)).normal(0, 5.0, a.shape)  # grain
    a = np.clip(a, 0, 255).astype(np.uint8)
    rgb = np.stack([a, (a * 0.985).astype(np.uint8), (a * 0.94).astype(np.uint8)], axis=-1)   # warm paper
    return Image.fromarray(rgb, "RGB")


def make_scan(src, dst, dpi=150, seed=7):
    rng = random.Random(seed)
    with pdfplumber.open(src) as pdf:
        pages = [_scan_page(p.to_image(resolution=dpi).original, rng) for p in pdf.pages]
    pages[0].save(dst, "PDF", resolution=dpi, save_all=True, append_images=pages[1:], quality=72)
    return len(pages)


if __name__ == "__main__":
    print(make_scan(sys.argv[1], sys.argv[2]), "pages written")
