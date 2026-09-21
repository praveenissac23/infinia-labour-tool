"""A signature the size the paper can use, and the shape it was written.

Run: cd app && DATABASE_URL=sqlite:////tmp/sg.db python3 ../tests/signature_test.py

A phone photograph of a signature runs to most of a megabyte and thirty
times the pixels a 34mm print can show. Every purchase order then paid
to scale it down again, and it rode along in every backup. It is
brought to a sensible size on the way in, kept in whichever format
suits the picture, and printed in its own proportions instead of being
stretched to fill the box.
"""
import sys, io, os, warnings
warnings.simplefilter('ignore')
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from PIL import Image
import database, models, auth, export_web
models.Base.metadata.create_all(database.engine)
import main

db = database.SessionLocal()
db.add(models.User(username='admin', hashed_password=auth.hash_password('p'), full_name='Praveen', role='admin'))
db.add(models.Site(code='901', active=True))
db.commit(); db.close()
c = TestClient(main.app, raise_server_exceptions=False)
H = {'Authorization': 'Bearer ' + c.post('/auth/login', data={'username': 'admin', 'password': 'p'}).json()['access_token']}
FAIL = []
def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{str(x)[:150]}]'))
    if not ok: FAIL.append(l)

for p in export_web.SIG_PATHS:
    if os.path.exists(p): os.remove(p)

def upload(img, name, fmt='PNG', **kw):
    b = io.BytesIO(); img.save(b, format=fmt, **kw)
    return c.post('/store/purchase/signature', files={'file': (name, b.getvalue())}, headers=H), len(b.getvalue())

# ---- A phone photograph: big, colour, no transparency ----------------
photo = Image.effect_noise((1683, 935), 40).convert('RGB')
r, sent = upload(photo, 'IMG_4471.jpg', 'JPEG', quality=95)
ck('the photo uploads', r.status_code == 200, r.text[:160])
kept = export_web.signature_file()
ck('it is kept as a photograph, not a lossless copy', kept.endswith('.jpg'), kept)
ck('brought down to a size the paper can use',
   max(Image.open(kept).size) <= main.SIGNATURE_MAX_PX, Image.open(kept).size)
ck(f'much smaller than what was sent ({sent//1024} KB in)',
   os.path.getsize(kept) < sent * 0.5, f'{os.path.getsize(kept)//1024} KB out')
ck('the app reports it as present',
   c.get('/store/purchase/signature-status', headers=H).json()['present'] is True)

# ---- A signature cut out with transparency keeps it ------------------
cut = Image.new('RGBA', (900, 300), (0, 0, 0, 0))
cut.putpixel((5, 5), (0, 0, 0, 255))
r, _ = upload(cut, 'signature.png')
ck('a cut-out signature uploads', r.status_code == 200, r.text[:160])
kept = export_web.signature_file()
ck('and stays a PNG, so its transparency survives', kept.endswith('.png'), kept)
ck('transparency really is still there', Image.open(kept).mode in ('RGBA', 'LA'))
ck('only one signature is held at a time',
   sum(os.path.exists(p) for p in export_web.SIG_PATHS) == 1,
   [p for p in export_web.SIG_PATHS if os.path.exists(p)])

# ---- Printed in its own proportions ----------------------------------
w, h = export_web._fit_box(kept, 34, 13)
src_w, src_h = Image.open(kept).size
ck("the print keeps the signature's proportions",
   abs((w / h) - (src_w / src_h)) < 0.01, f'{w/h:.2f} vs {src_w/src_h:.2f}')
ck('and stays inside the space it is given', w <= 34.01 and h <= 13.01, (w, h))

# ---- A real order still prints, with the signature on it -------------
item = c.post('/store/items', json={'name': 'Cement OPC 50kg', 'unit': 'bag', 'item_type': 'consumable'}, headers=H).json()
po = c.post('/store/purchase/orders', json={'order_date': '2026-09-21', 'supplier_name': 'Al Raha Trading LLC',
    'lines': [{'item_id': item['id'], 'description': 'Cement OPC 50kg', 'qty': 100, 'unit': 'bag',
               'rate': 16.5, 'tax_pct': 5}]}, headers=H)
ck('an order can be raised', po.status_code == 200, po.text[:160]); po = po.json()
tok = c.post('/auth/download-token', headers=H).json()['token']
pdf = c.get(f"/export/purchase/{po['id']}?token={tok}&format=pdf")
ck('the purchase order prints with a signature on it',
   pdf.status_code == 200 and pdf.content[:4] == b'%PDF', f'{pdf.status_code} {pdf.content[:30]}')
xl = c.get(f"/export/purchase/{po['id']}?token={tok}&format=excel")
ck('and the Excel copy builds with it too', xl.status_code == 200 and len(xl.content) > 2000, xl.status_code)

# ---- The imaging library missing must not stop an upload -------------
import builtins
real_import = builtins.__import__
def no_pil(name, *a, **k):
    if name == 'PIL' or name.startswith('PIL.'):
        raise ImportError('no PIL')
    return real_import(name, *a, **k)
builtins.__import__ = no_pil
try:
    raw = io.BytesIO(); Image.new('RGB', (40, 20), 'white').save(raw, format='PNG')
    r = c.post('/store/purchase/signature', files={'file': ('sig.png', raw.getvalue())}, headers=H)
    ck('an upload still works without the imaging library', r.status_code == 200, r.text[:160])
finally:
    builtins.__import__ = real_import

for p in export_web.SIG_PATHS:
    if os.path.exists(p): os.remove(p)
print('\n' + ('ALL PASS' if not FAIL else f'{len(FAIL)} FAILED: ' + '; '.join(FAIL)))
sys.exit(1 if FAIL else 0)
