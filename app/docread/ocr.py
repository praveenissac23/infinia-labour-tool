"""Scanned pages and photos: classic Tesseract OCR (no neural model is downloaded - Tesseract's own English data).

  1. the page is rendered (pdftoppm) at 300 dpi in grey;
  2. straightened: the angle whose row profile is sharpest (within +/-4 degrees) is taken, and the page turned back;
  3. table rules (long straight dark runs, far longer than any letter) are found - their positions split cells -
     and painted out, as a rule read as "|" or "1" spoils the figure beside it;
  4. Tesseract reads the page and gives every word with its box and confidence (TSV);
  5. figures it was unsure of are read again on their own, enlarged, with only digits allowed.

Pages are read two at a time (the server has two cores). Needs: tesseract-ocr (+ eng data) and poppler-utils.
"""
import io
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .model import Word
from .pdf import words_to_rows

TESS = os.environ.get("DOCREAD_TESSERACT", "tesseract")
ENV = dict(os.environ, OMP_THREAD_LIMIT="1")


def _runs(mask, k, axis):
    """Pixels that belong to a straight run of at least k dark pixels along an axis (a morphological opening with a
    1 x k line, done with cumulative sums - numpy only)."""
    m = mask.astype(np.int32)
    if axis == 1:
        m = m.T
    n = m.shape[0]
    if n < k:
        return np.zeros_like(mask)
    cs = np.vstack([np.zeros((1, m.shape[1]), np.int32), np.cumsum(m, axis=0)])
    full = (cs[k:] - cs[:-k]) == k            # windows of k all dark: start positions 0..n-k
    out = np.zeros_like(m, dtype=bool)
    # dilate back: a pixel is on a run if any window covering it is full
    cf = np.vstack([np.zeros((1, m.shape[1]), np.int32), np.cumsum(full.astype(np.int32), axis=0)])
    for_i = np.arange(n)
    lo = np.clip(for_i - k + 1, 0, full.shape[0])
    hi = np.clip(for_i + 1, 0, full.shape[0])
    out = (cf[hi] - cf[lo]) > 0
    if axis == 1:
        out = out.T
    return out


def _otsu(a):
    hist = np.bincount(a.ravel(), minlength=256).astype(np.float64)
    tot = a.size
    sum_all = np.dot(np.arange(256), hist)
    wb = np.cumsum(hist)
    sb = np.cumsum(hist * np.arange(256))
    wf = tot - wb
    with np.errstate(divide="ignore", invalid="ignore"):
        mb = sb / wb
        mf = (sum_all - sb) / wf
        between = wb * wf * (mb - mf) ** 2
    between = np.nan_to_num(between)
    return int(np.argmax(between))


def deskew_angle(img):
    """The page's tilt in degrees: the angle at which the rows of text make the sharpest horizontal profile."""
    small = img.copy()
    small.thumbnail((900, 900))
    a = np.asarray(small, dtype=np.uint8)
    t = _otsu(a)
    dark = Image.fromarray(((a < t) * 255).astype(np.uint8))
    best, best_s = 0.0, -1.0
    for coarse in (np.arange(-4.0, 4.01, 0.5), None):
        cands = coarse if coarse is not None else np.arange(best - 0.5, best + 0.51, 0.1)
        for ang in cands:
            r = np.asarray(dark.rotate(float(ang), resample=Image.NEAREST, fillcolor=0), dtype=np.float32)
            prof = r.sum(axis=1)
            s = float(np.sum(np.diff(prof) ** 2))
            if s > best_s:
                best, best_s = float(ang), s
    return best


def prepare(img):
    """Grey, straightened, rules out. Returns (image for Tesseract, vertical rules [(x, y0, y1)] in pixels, angle)."""
    img = ImageOps.grayscale(img)
    if img.width < 1600:                           # a small photo / low-dpi scan: enlarge so letters are ~30 px high
        k = 1800 / img.width
        img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
    ang = deskew_angle(img)
    if abs(ang) >= 0.15:
        img = img.rotate(ang, resample=Image.BICUBIC, fillcolor=255, expand=False)
    a = np.asarray(img, dtype=np.uint8)
    t = _otsu(a)
    dark = a < max(t, 60)
    h, w = dark.shape
    hk, vk = max(60, w // 12), max(40, h // 25)
    hor = _runs(dark, hk, axis=1)
    ver = _runs(dark, vk, axis=0)
    rules = []
    if ver.any():
        cols = np.where(ver.any(axis=0))[0]
        if cols.size:
            groups = np.split(cols, np.where(np.diff(cols) > 3)[0] + 1)
            for g in groups:
                x = int(g.mean())
                ys = np.where(ver[:, g].any(axis=1))[0]
                rules.append((x, int(ys.min()), int(ys.max())))
    lines = hor | ver
    if lines.any():
        # thicken by one pixel so the anti-aliased edge of a rule goes too
        lines = lines | np.roll(lines, 1, 0) | np.roll(lines, -1, 0) | np.roll(lines, 1, 1) | np.roll(lines, -1, 1)
        a = a.copy()
        a[lines] = 255
    return Image.fromarray(a), rules, ang


def _tsv(img, psm=6, extra=()):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    cmd = [TESS, "stdin", "stdout", "--psm", str(psm), "-c", "preserve_interword_spaces=1", *extra, "tsv"]
    p = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, env=ENV, timeout=120)
    out = []
    for line in p.stdout.decode("utf-8", "replace").splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12 or f[0] != "5":
            continue
        txt = f[11].strip()
        if not txt:
            continue
        x, y, w, h, conf = int(f[6]), int(f[7]), int(f[8]), int(f[9]), float(f[10])
        out.append((txt, x, y, x + w, y + h, conf, (int(f[2]), int(f[3]), int(f[4]))))
    return out


NUMTOK = re.compile(r"^[(\-]?[\dOoIlSB|.,]{3,}[)\-]?%?$")


def _reread_numbers(img, words):
    """Figures Tesseract was unsure of: each cropped, enlarged x2 and read again with only digits allowed, all in one
    Tesseract call (the crops stacked one under another)."""
    todo = [i for i, w in enumerate(words) if NUMTOK.match(w[0]) and sum(ch.isdigit() for ch in w[0]) >= 2 and w[5] < 85]
    if not todo:
        return words
    crops, pad = [], 6
    for i in todo:
        t, x0, y0, x1, y1 = words[i][:5]
        c = img.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad))
        c = c.resize((c.width * 2, c.height * 2), Image.LANCZOS)
        crops.append(c)
    W = max(c.width for c in crops) + 40
    gap = 30
    H = sum(c.height + gap for c in crops) + gap
    sheet = Image.new("L", (W, H), 255)
    y, spans = gap, []
    for c in crops:
        sheet.paste(c, (20, y))
        spans.append((y, y + c.height))
        y += c.height + gap
    got = _tsv(sheet, psm=6, extra=("-c", "tessedit_char_whitelist=0123456789.,()-%"))
    words = list(words)
    for k, (a, b) in enumerate(spans):
        mine = [g for g in got if a - 5 <= (g[2] + g[4]) / 2 <= b + 5]
        if not mine:
            continue
        txt = "".join(g[0] for g in sorted(mine, key=lambda g: g[1]))
        conf = min(g[5] for g in mine)
        i = todo[k]
        old = words[i]
        if conf > old[5] and re.search(r"\d", txt):
            words[i] = (txt,) + old[1:5] + (conf,) + old[6:]
    return words


def ocr_image(img, page, scale=1.0, reread=True):
    """One page picture -> rows of cells (coordinates in points: pixels x scale)."""
    prep, rules, ang = prepare(img)
    raw = _tsv(prep, psm=6)
    # psm 6 reads a page as one block; where it found little (a sparse form), psm 11 finds scattered words
    if len(raw) < 15:
        raw2 = _tsv(prep, psm=11)
        if len(raw2) > len(raw):
            raw = raw2
    if reread:
        raw = _reread_numbers(prep, raw)
    words = []
    for t, x0, y0, x1, y1, conf, _ in raw:
        if conf < 10 and not re.search(r"\d", t):
            continue
        if re.fullmatch(r"[|\[\]{}~=_—–\\/]+", t):
            continue
        t = t.strip("|[]")
        if not t:
            continue
        words.append(Word(t, x0 * scale, y0 * scale, x1 * scale, y1 * scale, max(0.0, min(1.0, conf / 100.0))))
    rr = [(x * scale, y0 * scale, y1 * scale) for x, y0, y1 in rules]
    return words_to_rows(words, page, rr, ocr=True, gap_k=1.0)


def render_pdf_pages(data, pages, dpi=300):
    """pdftoppm -> {page: PIL image}."""
    out = {}
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.pdf")
        with open(src, "wb") as fh:
            fh.write(data)
        for pn in pages:
            prefix = os.path.join(d, f"p{pn}")
            subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-f", str(pn), "-l", str(pn), "-singlefile", src, prefix],
                           capture_output=True, timeout=120)
            fn = prefix + ".png"
            if os.path.exists(fn):
                im = Image.open(fn)
                im.load()
                out[pn] = im
    return out


def ocr_pdf_pages(data, pages, dpi=300, parallel=2):
    imgs = render_pdf_pages(data, pages, dpi)
    scale = 72.0 / dpi

    def one(pn):
        return pn, ocr_image(imgs[pn], pn, scale)
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        return dict(ex.map(one, [p for p in pages if p in imgs]))


def read_image(data, name=""):
    from .model import Doc, Region
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    frames = []
    try:
        for i in range(getattr(img, "n_frames", 1)):
            img.seek(i)
            frames.append(img.convert("L"))
    except Exception:
        frames = [img.convert("L")]
    regions = []
    for i, fr in enumerate(frames):
        dpi = (img.info.get("dpi") or (300, 300))[0] or 300
        rows = ocr_image(fr, i + 1, 72.0 / float(dpi))
        regions.append(Region(name=f"Page {i + 1}", page=i + 1, rows=rows, kind="scan"))
    return Doc(regions=regions, kind="image", name=name, ocr_pages=[r.page for r in regions])
