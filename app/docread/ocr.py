"""Scanned pages and photos: classic Tesseract OCR (no neural model is downloaded - Tesseract's own English data).

  1. the page is rendered (pdftoppm) at 300 dpi in grey;
  2. straightened: the angle whose row profile is sharpest (within +/-4 degrees) is taken, and the page turned back;
  3. table rules (long straight dark runs, far longer than any letter) are found - their positions split cells -
     and painted out, as a rule read as "|" or "1" spoils the figure beside it;
  4. Tesseract reads the page and gives every word with its box and confidence (TSV);
  5. figures it was unsure of are read again on their own, enlarged, with only digits allowed.

Pages are read one at a time by default (DOCREAD_PARALLEL=1: the server has about 1 GB of memory; 2 reads two at once). Needs: tesseract-ocr (+ eng data) and poppler-utils.
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
    ang = deskew_angle(img)
    if abs(ang) >= 0.15:
        img = img.rotate(ang, resample=Image.BICUBIC, fillcolor=255, expand=False)
    a = np.asarray(img, dtype=np.uint8)
    # rules are found on a half-size picture (4x less work), then painted out on the full one
    half = img.resize((img.width // 2, img.height // 2), Image.BOX)
    h_ = np.asarray(half, dtype=np.uint8)
    t = _otsu(h_)
    dark = h_ < max(t, 60)
    h, w = dark.shape
    hk, vk = max(30, w // 12), max(20, h // 25)
    hor = _runs(dark, hk, axis=1)
    ver = _runs(dark, vk, axis=0)
    rules = []
    if ver.any():
        cols = np.where(ver.any(axis=0))[0]
        if cols.size:
            groups = np.split(cols, np.where(np.diff(cols) > 2)[0] + 1)
            for g in groups:
                x = int(g.mean()) * 2
                ys = np.where(ver[:, g].any(axis=1))[0]
                rules.append((x, int(ys.min()) * 2, int(ys.max()) * 2))
    hrules = []
    if hor.any():
        rws = np.where(hor.any(axis=1))[0]
        for g in np.split(rws, np.where(np.diff(rws) > 2)[0] + 1):
            xs = np.where(hor[g, :].any(axis=0))[0]
            hrules.append((int(g.mean()) * 2, int(xs.min()) * 2, int(xs.max()) * 2))
    lines = hor | ver
    if lines.any():
        m = Image.fromarray((lines * 255).astype(np.uint8)).resize(img.size, Image.NEAREST).filter(ImageFilter.MaxFilter(7))
        mask = np.asarray(m) > 0
        a = a.copy()
        a[mask] = 255
    return Image.fromarray(a), rules, ang, hrules


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


def _split_on_rules(raw, rules):
    """A word Tesseract read across a column rule ("2025:.14") is two cells' text: cut where the rule runs
    (letters taken as equally wide), the rule's remains (| ! : .) dropped at the cut."""
    out = []
    for wd in raw:
        t, x0, y0, x1, y1 = wd[:5]
        cuts = [x for x, ry0, ry1 in rules if x0 + 4 < x < x1 - 4 and ry0 - 5 <= (y0 + y1) / 2 <= ry1 + 5]
        if not cuts or len(t) < 2:
            out.append(wd)
            continue
        pos, prev_x = 0, x0
        for x in sorted(cuts) + [x1]:
            k = round(len(t) * (x - x0) / max(1, x1 - x0))
            piece = t[pos:k].strip("|!:;.,'`") if x != x1 else t[pos:].strip("|!:;'`")
            if piece:
                out.append((piece, int(prev_x), y0, int(x), y1) + tuple(wd[5:]))
            pos, prev_x = k, x
    return out


def ocr_image(img, page, scale=1.0, reread=True, with_rules=False):
    """One page picture -> rows of cells (coordinates in points: pixels x scale)."""
    if img.width < 2000:              # a low-resolution scan or photo: enlarged to about 300 dpi for Tesseract
        k = 2480 / img.width
        img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
        scale /= k
    prep, rules, ang, hrules = prepare(img)
    raw = _tsv(prep, psm=6)
    # psm 6 reads a page as one block; where it found little (a sparse form), psm 11 finds scattered words
    if len(raw) < 15:
        raw2 = _tsv(prep, psm=11)
        if len(raw2) > len(raw):
            raw = raw2
    if reread:
        raw = _reread_numbers(prep, raw)
    raw = _split_on_rules(raw, rules)
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
    rows = words_to_rows(words, page, rr, ocr=True, gap_k=1.0)
    hr = [(y * scale, x0 * scale, x1 * scale) for y, x0, x1 in hrules]
    if with_rules:
        return rows, rr, hr
    from .model import Region, merge_bands
    return merge_bands(Region(name="", page=page, rows=rows, kind="scan", hrules=hr)).rows


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


def embedded_scans(data, pages):
    """A scanned page is usually one JPEG covering the page: taken out as it is (no re-rendering, its own
    resolution) -> {page: (image, points per pixel)}. Pages that are not like that are left for pdftoppm."""
    import pdfplumber
    out = {}
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for pn in pages:
                page = pdf.pages[pn - 1]
                ims = page.images
                if len(ims) != 1:
                    continue
                im = ims[0]
                if (im["x1"] - im["x0"]) < 0.8 * float(page.width) or (im["bottom"] - im["top"]) < 0.8 * float(page.height):
                    continue
                st = im["stream"]
                flt = st.get_filters() if hasattr(st, "get_filters") else []
                names = [str(f[0]) if isinstance(f, tuple) else str(f) for f in flt]
                if not any("DCT" in n for n in names):
                    continue
                raw = st.get_rawdata() if hasattr(st, "get_rawdata") else st.rawdata
                pic = Image.open(io.BytesIO(raw))
                pic.load()
                out[pn] = (pic.convert("L"), (im["x1"] - im["x0"]) / pic.width)
    except Exception:
        return out
    return out


def ocr_pdf_pages(data, pages, dpi=300, parallel=None):
    if parallel is None:                 # pages read at once (DOCREAD_PARALLEL=1 on a small server keeps memory down)
        parallel = int(os.environ.get("DOCREAD_PARALLEL", "1") or 1)
    got = embedded_scans(data, pages)
    imgs = {pn: x[0] for pn, x in got.items()}
    scales = {pn: x[1] for pn, x in got.items()}
    rest = [p for p in pages if p not in imgs]
    if rest:
        for pn, im in render_pdf_pages(data, rest, dpi).items():
            imgs[pn], scales[pn] = im, 72.0 / dpi

    def one(pn):
        return pn, ocr_image(imgs[pn], pn, scales[pn], with_rules=True)
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
        sc = 72.0 / float(dpi)
        rows, rr, hr = ocr_image(fr, i + 1, sc, with_rules=True)
        from .model import merge_bands
        regions.append(merge_bands(Region(name=f"Page {i + 1}", page=i + 1, rows=rows, kind="scan", vrules=rr, hrules=hr,
                                          width=round(fr.width * sc, 1), height=round(fr.height * sc, 1))))
    return Doc(regions=regions, kind="image", name=name, ocr_pages=[r.page for r in regions])
