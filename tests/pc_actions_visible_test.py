"""Subcontract > Payment certificates: Print and Delete stay on screen at the right edge of the table, however many
columns there are (21/11/2026: on a laptop they were past the edge, behind a sideways scroll). Checked in a browser
where there is one; the source check runs everywhere."""
import os, sys, re, subprocess, tempfile
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  {x}'))
    if not ok: FAIL.append(l)
js = open(os.path.join(ROOT, "portal/est/est.js"), encoding="utf-8").read()
css = open(os.path.join(ROOT, "portal/est/est.css"), encoding="utf-8").read()
built = open(os.path.join(ROOT, "portal/est-app.html"), encoding="utf-8").read()
ck("the Print / Delete cell is marked pcact", '<td class="pcact"><button class="btn btn-plain btn-sm" data-print=' in js)
ck("its header too", '<th>Status</th><th class="pcact"></th>' in js)
ck("pcact sticks to the right", re.search(r"td\.pcact\s*\{[^}]*position:\s*sticky;\s*right:\s*0", css) is not None)
import hashlib
v = lambda f: hashlib.md5(open(os.path.join(ROOT, f), "rb").read()).hexdigest()[:10]
ck("the built page loads the new est.js / est.css (version stamps up to date)", f"est.js?v=" in built and f"est.css?v=" in built)
# 24/11/2026: every script of the estimation page is loaded under the stamp of its current contents - a stale stamp
# keeps phones on the old script (the certificate note box would not show)
import hashlib as _hl, re as _re, glob as _gl
_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_page = open(os.path.join(_root, "portal", "est-app.html"), encoding="utf-8").read()
_stale = []
for _src, _v in _re.findall(r'(/portal/est/[\w.-]+\.(?:js|css))\?v=(\w+)', _page):
    _fp = os.path.join(_root, _src.lstrip("/"))
    if os.path.exists(_fp) and _v not in (_hl.sha1(open(_fp, "rb").read()).hexdigest()[:10], _hl.md5(open(_fp, "rb").read()).hexdigest()[:10]):
        _stale.append(_src)
ck("estimation page: every script stamp matches its file (run deploy/build_temporary_pages.py)", not _stale, _stale)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP browser check - no browser here")
else:
    th = "".join(f"<th class=r>Column {i} long header</th>" for i in range(13))
    td = "".join("<td class=r>40,829.25</td>" for _ in range(13))
    html = (f"<html><head><style>{css}</style></head><body><div class=wrap style='width:1100px'><div class=card><div class=tw><table class=t><thead><tr>{th}"
            f"<th class=pcact></th></tr></thead><tbody><tr class=rowc>{td}<td class=pcact><button class='btn btn-plain btn-sm'>Print</button>"
            "<button class='btn btn-ghost btn-sm'>Delete</button></td></tr></tbody></table></div></div></div></body></html>")
    f = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False); f.write(html); f.close()
    with sync_playwright() as pw:
        b = pw.chromium.launch(); p = b.new_page(viewport={"width": 1200, "height": 400}); p.goto("file://" + f.name)
        r = p.evaluate("(() => { const c = document.querySelector('td.pcact').getBoundingClientRect(), w = document.querySelector('.tw').getBoundingClientRect(), t = document.querySelector('table.t').getBoundingClientRect(); return [c.left, c.right, w.right, t.right]; })()")
        ck("table wider than its box, buttons still inside the box", r[3] > r[2] and r[1] <= r[2] + 1 and r[0] < r[2], r)
        b.close()
    os.unlink(f.name)
print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED'))
sys.exit(1 if FAIL else 0)
