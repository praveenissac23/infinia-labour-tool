"""Ask the app anything, from Claude - a read-only connector (MCP).

An admin turns it on in Settings and gets a private link; that link is
added to Claude as a custom connector. Claude then answers questions
about the app ("LPOs sent in the last 50 days", "every increment, all
companies") by reading the database through three tools:

  tables  - what is kept, one line a table; with names, their columns
  query   - one read-only SELECT, the rows back as short text
  report  - the same, built into Excel / PDF here, only a link goes back

Built to spend few tokens: short descriptions, results as tab-separated
text, capped rows, long lists sent as a file link instead of rows.

Safe on the live database: only SELECT is accepted, it runs in a
read-only transaction with a time limit, secrets (passwords, keys,
device addresses) are never shown, it works for admin logins only, and
every question goes into the activity log.

Plain JSON-RPC over HTTP (MCP "streamable HTTP", JSON answers) written
out here - nothing new to install on the server.
"""
import hmac
import os
import re
import secrets
import time
from collections import deque
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

import main as M
import models, auth, export_web
from database import Base, engine, get_db, SessionLocal

router = APIRouter()
PREFIX = "/reports/ask"          # under /reports/ so the live nginx already forwards it
KEY_PREFIX = "agent_key:"
FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_files")
FILE_HOURS = 24
DEFAULT_ROWS, MAX_ROWS, REPORT_ROWS = 50, 200, 5000
CELL = 80                        # characters a cell is cut to in a reply
PER_MINUTE = 60

# Never shown, whatever is asked.
HIDDEN_TABLES = {"settings", "push_subscriptions", "push_sent", "alembic_version", "backups"}
HIDDEN_COL = re.compile(r"password|secret|token|vapid|p256dh|endpoint|^auth$", re.I)
WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|merge|upsert|drop|alter|create|truncate|grant|revoke|copy|set|reset|"
    r"begin|commit|rollback|savepoint|release|vacuum|analyze|call|do|lock|listen|notify|unlisten|"
    r"prepare|execute|deallocate|refresh|cluster|reindex|comment|security|attach|detach|pragma|into)\b"
    r"|pg_|dblink|\blo_|current_setting|set_config|password|secret|token|vapid|p256dh", re.I)
BCRYPT = re.compile(r"^\$2[aby]?\$\d\d\$")


# ---- The key: a private link per admin --------------------------------------

def _key_row(db, user_id):
    return db.query(models.Setting).filter(models.Setting.key == f"{KEY_PREFIX}{user_id}").first()


def _user_for_key(db, key):
    if not key or len(key) < 20:
        return None
    for row in db.query(models.Setting).filter(models.Setting.key.like(KEY_PREFIX + "%")).all():
        if row.value and hmac.compare_digest(row.value, key):
            try:
                uid = int(row.key[len(KEY_PREFIX):])
            except ValueError:
                return None
            u = db.query(models.User).filter(models.User.id == uid).first()
            if u and u.role == "admin" and getattr(u, "active", True) is not False:
                return u
            return None
    return None


def _base_url(request: Request, db=None):
    """The app's public address. Behind nginx the request may only say
    127.0.0.1, so the address the admin's browser was on when the link
    was made is kept and used first."""
    try:
        own = db or SessionLocal()
        try:
            row = own.query(models.Setting).filter(models.Setting.key == "agent_base").first()
        finally:
            if db is None:
                own.close()
        if row and row.value:
            return row.value
    except Exception:
        pass
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "app.infinia.ae"
    proto = request.headers.get("x-forwarded-proto")
    if not proto:
        proto = "http" if host.startswith(("127.", "localhost")) else "https"
    return f"{proto}://{host}"


def _admin(user):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin login can connect Claude to the app.")


@router.get(PREFIX + "/link")
def agent_status(request: Request, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.get_current_user)):
    _admin(user)
    row = _key_row(db, user.id)
    return {"on": bool(row and row.value),
            "url": f"{_base_url(request, db)}{PREFIX}/mcp/{row.value}" if row and row.value else ""}


@router.post(PREFIX + "/link")
def agent_new_link(request: Request, payload: dict = Body(default={}), db: Session = Depends(get_db),
                   user: models.User = Depends(auth.get_current_user)):
    """A new private link - the old one stops working at once."""
    _admin(user)
    origin = str((payload or {}).get("origin") or "").strip().rstrip("/")
    if re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d+)?", origin):
        b = db.query(models.Setting).filter(models.Setting.key == "agent_base").first()
        if b:
            b.value = origin
        else:
            db.add(models.Setting(key="agent_base", value=origin))
    key = secrets.token_urlsafe(32)
    row = _key_row(db, user.id)
    if row:
        row.value = key
    else:
        db.add(models.Setting(key=f"{KEY_PREFIX}{user.id}", value=key))
    db.commit()
    M.log_action(db, user.id, "agent_link", "Claude connector link made")
    return {"on": True, "url": f"{_base_url(request, db)}{PREFIX}/mcp/{key}"}


@router.delete(PREFIX + "/link")
def agent_off(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    _admin(user)
    row = _key_row(db, user.id)
    if row:
        db.delete(row); db.commit()
    M.log_action(db, user.id, "agent_off", "Claude connector turned off")
    return {"on": False, "url": ""}


# ---- What is kept: the tables, short ---------------------------------------

def _docs():
    """Each table's meaning, from the first lines of its model's docstring."""
    out = {}
    for m in Base.registry.mappers:
        cls = m.class_
        t = getattr(cls, "__tablename__", None)
        if not t:
            continue
        doc = " ".join((cls.__doc__ or "").strip().split("\n\n")[0].split())
        if doc:
            out[t] = doc if len(doc) <= 90 else doc[:88].rsplit(" ", 1)[0] + "…"
    return out


def _short_type(t):
    s = str(t).lower()
    for a, b in (("int", "int"), ("numeric", "num"), ("float", "num"), ("double", "num"), ("real", "num"),
                 ("bool", "bool"), ("timestamp", "datetime"), ("datetime", "datetime"), ("date", "date"),
                 ("char", "text"), ("text", "text"), ("json", "json")):
        if a in s:
            return b
    return s.split("(")[0]


def tables_text(names=None):
    ins = sa_inspect(engine)
    have = [t for t in sorted(ins.get_table_names()) if t not in HIDDEN_TABLES]
    if not names:
        docs = _docs()
        return "\n".join(f"{t}: {docs.get(t, '')}".rstrip(": ") for t in have)
    out = []
    for t in names:
        t = str(t).strip()
        if t not in have:
            out.append(f"{t}: no such table")
            continue
        fks = {}
        for fk in ins.get_foreign_keys(t):
            for c in fk.get("constrained_columns") or []:
                fks[c] = fk.get("referred_table")
        cols = [f"{c['name']} {_short_type(c['type'])}" + (f"→{fks[c['name']]}" if c["name"] in fks else "")
                for c in ins.get_columns(t) if not HIDDEN_COL.search(c["name"])]
        out.append(f"{t}({', '.join(cols)})")
    return "\n".join(out)


# ---- Running a question, read-only -----------------------------------------

def _strip_literals(sql):
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_sql(sql):
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("Empty query.")
    bare = _strip_literals(s)
    bare = re.sub(r"--[^\n]*|/\*.*?\*/", " ", bare, flags=re.S)
    if ";" in bare:
        raise ValueError("One statement at a time.")
    if not re.match(r"^\s*(select|with)\b", bare, re.I):
        raise ValueError("Only SELECT (or WITH ... SELECT) is allowed - this connection only reads.")
    bad = WRITE_WORDS.search(bare)
    if bad:
        raise ValueError(f"Not allowed here: {bad.group(0)}")
    hidden = re.search(r"\b(" + "|".join(HIDDEN_TABLES) + r")\b", bare, re.I)
    if hidden:
        raise ValueError(f"{hidden.group(1)} is not available.")
    return s


def run_sql(sql, limit):
    s = check_sql(sql)
    pg = engine.dialect.name == "postgresql"
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            if pg:
                conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                conn.exec_driver_sql("SET LOCAL statement_timeout = 8000")
            else:
                conn.exec_driver_sql("PRAGMA query_only = ON")
            # The driver's own cursor, given no parameters, sends the text as
            # it is - a % in LIKE '%x%' is not taken for a placeholder.
            cur = conn.connection.dbapi_connection.cursor()
            try:
                cur.execute(s)
                cols = [d[0] for d in (cur.description or [])]
                rows = cur.fetchmany(limit + 1) if cols else []
            finally:
                cur.close()
        finally:
            trans.rollback()
            if not pg:
                conn.exec_driver_sql("PRAGMA query_only = OFF")
    keep = [i for i, c in enumerate(cols) if not HIDDEN_COL.search(str(c))]
    cols = [cols[i] for i in keep]
    rows = [[_clean(r[i]) for i in keep] for r in rows]
    more = len(rows) > limit
    return cols, rows[:limit], more


def _clean(v):
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        v = round(v, 2)
        return int(v) if v.is_integer() else v
    if isinstance(v, (datetime, date)):
        return v.isoformat()[:16] if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, (bytes, memoryview)):
        return "[binary]"
    if isinstance(v, str) and BCRYPT.match(v):
        return "[hidden]"
    return v


def _cell(v):
    if v is None:
        return ""
    s = str(v).replace("\t", " ").replace("\n", " ")
    return s if len(s) <= CELL else s[:CELL - 1] + "…"


def rows_text(cols, rows, more):
    if not rows:
        return "0 rows."
    out = ["\t".join(map(str, cols))] + ["\t".join(_cell(v) for v in r) for r in rows]
    out.append(f"(first {len(rows)} rows - more exist: aggregate, filter, or use report for the full list)"
               if more else f"({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return "\n".join(out)


# ---- A full list as a file --------------------------------------------------

def make_report(sql, title, fmt, base):
    cols, rows, more = run_sql(sql, REPORT_ROWS)
    os.makedirs(FILES, exist_ok=True)
    cutoff = time.time() - FILE_HOURS * 3600
    for f in os.listdir(FILES):
        p = os.path.join(FILES, f)
        try:
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass
    title = (title or "Report").strip()[:80]
    data = [dict(zip(cols, r)) for r in rows] or [{"": "Nothing found."}]
    sub = f"{len(rows)} rows" + (" (first 5,000)" if more else "") + f"   |   {M._dubai_today():%d %b %Y}"
    fmt = "pdf" if str(fmt).lower() == "pdf" else "excel"
    buf = (export_web.build_store_report_pdf(title, data, sub) if fmt == "pdf"
           else export_web.build_store_report_excel(title, data, sub))
    fid = secrets.token_urlsafe(16)
    ext = "pdf" if fmt == "pdf" else "xlsx"
    with open(os.path.join(FILES, f"{fid}.{ext}"), "wb") as fh:
        fh.write(buf.getvalue() if hasattr(buf, "getvalue") else buf.read())
    return (f"{base}{PREFIX}/file/{fid}.{ext}\n{len(rows)} rows" + (" (capped at 5,000)" if more else "")
            + f"; columns: {', '.join(map(str, cols))}. Link works for {FILE_HOURS} hours.")


@router.get(PREFIX + "/file/{name}")
def agent_file(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,40}\.(pdf|xlsx)", name):
        raise HTTPException(status_code=404, detail="Not found.")
    p = os.path.join(FILES, name)
    if not os.path.exists(p) or os.path.getmtime(p) < time.time() - FILE_HOURS * 3600:
        raise HTTPException(status_code=404, detail="This link has expired - ask again for a fresh one.")
    nice = "Infinia_Report." + name.rsplit(".", 1)[1]
    media = "application/pdf" if name.endswith(".pdf") else \
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(p, media_type=media, filename=nice)


# ---- The MCP conversation ---------------------------------------------------

def _instructions():
    sql = "PostgreSQL" if engine.dialect.name == "postgresql" else "SQLite"
    return (f"Infinia Contracting (Dubai) app data, read-only, {sql}. Today in Dubai: {M._dubai_today():%Y-%m-%d}. "
            "Call tables once, then tables with names for the columns you need, then query. "
            "Money is AED. employees.staff false = labour, true = office staff (pay_group 'local' = local staff). "
            "Payroll cycles run 26th to 25th, named by the ending month ('October 2026' = 26 Sep-25 Oct). "
            "Keep replies small: COUNT/SUM/GROUP BY rather than listing rows; for full lists use report (Excel/PDF link).")


TOOLS = [
    {"name": "tables",
     "description": "List the app's tables, one line each. Pass names to get those tables' columns.",
     "inputSchema": {"type": "object", "properties": {
         "names": {"type": "array", "items": {"type": "string"}, "description": "Tables to show columns for"}}}},
    {"name": "query",
     "description": "Run one read-only SELECT. Returns tab-separated rows (default 50, max 200).",
     "inputSchema": {"type": "object", "required": ["sql"], "properties": {
         "sql": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": MAX_ROWS}}}},
    {"name": "report",
     "description": "Run a SELECT and build an Excel or PDF here; returns a download link, not the rows. Use for full lists.",
     "inputSchema": {"type": "object", "required": ["sql", "title"], "properties": {
         "sql": {"type": "string"}, "title": {"type": "string"},
         "format": {"type": "string", "enum": ["excel", "pdf"]}}}},
]

_CALLS = {}


def _slow_down(uid):
    q = _CALLS.setdefault(uid, deque())
    now = time.time()
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= PER_MINUTE:
        return True
    q.append(now)
    return False


def _call(name, args, user, base):
    args = args or {}
    db = SessionLocal()
    try:
        if name == "tables":
            return tables_text(args.get("names"))
        if name == "query":
            try:
                limit = max(1, min(int(args.get("limit") or DEFAULT_ROWS), MAX_ROWS))
            except (TypeError, ValueError):
                limit = DEFAULT_ROWS
            M.log_action(db, user.id, "agent_query", str(args.get("sql", ""))[:500])
            return rows_text(*run_sql(args.get("sql", ""), limit))
        if name == "report":
            M.log_action(db, user.id, "agent_report", f"{args.get('title', '')}: {str(args.get('sql', ''))[:400]}")
            return make_report(args.get("sql", ""), args.get("title", ""), args.get("format", "excel"), base)
        raise ValueError(f"No tool called {name}.")
    finally:
        db.close()


VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


def _answer(msg, user, base):
    mid, method = msg.get("id"), msg.get("method", "")
    if mid is None:                        # a notification - nothing to say back
        return None
    p = msg.get("params") or {}
    if method == "initialize":
        want = p.get("protocolVersion")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": want if want in VERSIONS else VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "infinia-app", "version": "1.0"},
            "instructions": _instructions()}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        if _slow_down(user.id):
            text, err = "Too many questions in a minute - wait a moment.", True
        else:
            try:
                text, err = _call(p.get("name"), p.get("arguments"), user, base), False
            except ValueError as e:
                text, err = str(e), True
            except Exception as e:              # a bad column name, a timeout - said plainly, briefly
                text, err = ("Query failed: " + " ".join(str(getattr(e, "orig", e)).split())[:300]), True
        return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}], "isError": err}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown method {method}"}}


@router.post(PREFIX + "/mcp/{key}")
async def mcp(key: str, request: Request):
    db = SessionLocal()
    try:
        user = _user_for_key(db, key)
    finally:
        db.close()
    if not user:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {
            "code": -32001, "message": "This link is not valid any more - make a new one in Settings."}}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                            status_code=400)
    base = _base_url(request)
    if isinstance(body, list):
        out = [a for a in (_answer(m, user, base) for m in body if isinstance(m, dict)) if a]
        return JSONResponse(out) if out else Response(status_code=202)
    a = _answer(body if isinstance(body, dict) else {}, user, base)
    return JSONResponse(a) if a else Response(status_code=202)


@router.get(PREFIX + "/mcp/{key}")
def mcp_get(key: str):
    # No server-to-client stream: answers come back on each POST.
    return Response(status_code=405, headers={"Allow": "POST"})


@router.delete(PREFIX + "/mcp/{key}")
def mcp_end(key: str):
    return Response(status_code=200)
