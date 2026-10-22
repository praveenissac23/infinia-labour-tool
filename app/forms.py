"""Admin > Forms: the company's blank HR forms as PDFs - Preview, PDF, Share."""
import os
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

import auth
import export_web
import forms_pdf
import main as M
from database import get_db

router = APIRouter()
RIGHT = "admin_forms"
THUMBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "form_thumbs")


def _user(token, db):
    u = auth.get_download_user_from_token(token, db)
    if (u.role or "") != "admin" and RIGHT not in M.effective_permissions(u):
        raise HTTPException(status_code=403, detail="Ask an admin for Admin > Forms.")
    return u


@router.get("/store/admin/forms")
def list_forms(user=Depends(M.require_any_screen(RIGHT))):
    return {"forms": [{"key": k, "no": forms_pdf.FORMS[k]["no"], "title": forms_pdf.FORMS[k]["title"].title(),
                       "tag": forms_pdf.FORMS[k]["tag"], "intro": forms_pdf.FORMS[k]["intro"],
                       "sign": forms_pdf.FORMS[k]["sign"]} for k in forms_pdf.ORDER]}


@router.get("/export/admin/forms/{key}")
def form(key: str, token: str, format: str = "pdf", dl: int = 0, db: Session = Depends(get_db)):
    if key not in forms_pdf.FORMS:
        raise HTTPException(status_code=404, detail="No such form.")
    u = _user(token, db)
    f = forms_pdf.FORMS[key]
    name = f"{f['no'].replace('/', '-')}_{f['title'].title().replace(' ', '_')}_{f['tag'].split()[0]}"
    if format in ("thumb", "page"):
        p = os.path.join(THUMBS, key + ("_page" if format == "page" else "") + ".png")
        if not os.path.exists(p):
            raise HTTPException(status_code=404, detail="No picture of this form.")
        return FileResponse(p, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
    if format == "view":
        vt = quote(auth.create_view_token(u.username), safe="")
        pdf = f"/export/admin/forms/{key}?format=pdf&token={vt}"
        title = forms_pdf.title_of(key)
        return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{export_web.PREVIEW_BAR_CSS}
body{{margin:0;background:#E9E6E2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif}}
.pg{{max-width:860px;margin:18px auto 30px;padding:0 12px}} .pg img{{width:100%;display:block;background:#fff;box-shadow:0 2px 14px rgba(0,0,0,.12);border-radius:3px}}</style></head><body>
<div class="pvbar"><h1>{escape(title)}</h1><span class="who">{escape(f['no'])} &middot; blank form, one A4 page</span><span class="sp"></span>
<a class="btn dark" href="{pdf}&dl=1">Download PDF</a><a class="btn" href="{pdf}" target="_blank" rel="noopener">Print</a>{export_web.share_button(pdf, title)}</div>
<div class="pg"><img src="/export/admin/forms/{key}?format=page&token={vt}" alt="{escape(title)}"></div>
{export_web.SHARE_JS}</body></html>""")
    buf = forms_pdf.build(key)
    disp = "attachment" if dl else "inline"
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f'{disp}; filename="{name}.pdf"'})
