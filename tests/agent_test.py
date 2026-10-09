"""The Claude connector: speaks MCP, reads only, admin only, hides secrets."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("INFINIA_NO_PUSH", "1")
from fastapi.testclient import TestClient
import main, models, auth
from database import SessionLocal

db = SessionLocal()
if not db.query(models.User).filter(models.User.username == "boss").first():
    db.add(models.User(username="boss", hashed_password=auth.hash_password("p"), full_name="Boss", role="admin"))
    db.add(models.User(username="clerk", hashed_password=auth.hash_password("p"), full_name="Clerk", role="office",
                       permissions="attendance"))
    db.add(models.Employee(emp_no="T-1", name="TEST ONE", trade="MASON", basic_salary=1000, total_salary=1500, active=True))
    db.commit()
db.close()

c = TestClient(main.app)
FAIL = []
def ck(l, ok, x=""):
    print(("PASS " if ok else "FAIL ") + l + ("" if ok else f"  [{x}]"))
    if not ok: FAIL.append(l)
def tok(u):
    return {"Authorization": "Bearer " + c.post("/auth/login", data={"username": u, "password": "p"}).json()["access_token"]}
B, K = tok("boss"), tok("clerk")

ck("a non-admin cannot turn it on", c.post("/settings/agent", headers=K).status_code == 403)
ck("off to begin with", c.get("/settings/agent", headers=B).json()["on"] is False)
url = c.post("/settings/agent", headers=B).json()["url"]
path = url.split("://", 1)[1].split("/", 1)[1]; path = "/" + path
ck("admin gets a private link under /reports/", path.startswith("/reports/ask/mcp/") and len(path) > 50, path)

def rpc(method, params=None, i=1, p=path):
    r = c.post(p, json={"jsonrpc": "2.0", "id": i, "method": method, "params": params or {}})
    return r
def call(name, args):
    r = rpc("tools/call", {"name": name, "arguments": args}).json()["result"]
    return r["content"][0]["text"], r["isError"]

r = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}).json()
ck("initialize answers MCP", r["result"]["protocolVersion"] == "2025-06-18" and "tools" in r["result"]["capabilities"], r)
ck("short instructions", len(r["result"]["instructions"]) < 700, len(r["result"]["instructions"]))
ck("notification gets 202", c.post(path, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202)
tl = rpc("tools/list").json()["result"]["tools"]
ck("three tools", [t["name"] for t in tl] == ["tables", "query", "report"], [t["name"] for t in tl])
ck("GET is 405 (no stream)", c.get(path).status_code == 405)
ck("a wrong link is refused", rpc("tools/list", p="/reports/ask/mcp/" + "x" * 43).status_code == 404)

t, e = call("tables", {})
ck("tables lists employees with a meaning", "employees" in t and not e, t[:200])
ck("secret tables not listed", "\nsettings" not in "\n" + t and "push_subscriptions" not in t)
t, e = call("tables", {"names": ["users"]})
ck("users columns hide the password", "username" in t and "password" not in t, t)

t, e = call("query", {"sql": "SELECT emp_no, name, total_salary FROM employees WHERE emp_no = 'T-1'"})
ck("a SELECT comes back as short rows", "T-1\tTEST ONE\t1500" in t and not e, t)
t, e = call("query", {"sql": "select count(*) as n from employees"})
ck("count works", t.startswith("n\n") and not e, t)
t, e = call("query", {"sql": "SELECT * FROM users"})
ck("SELECT * FROM users drops the password column", "hashed_password" not in t and "$2" not in t and not e, t[:300])

for bad in ["DELETE FROM employees", "UPDATE employees SET name='x'", "DROP TABLE employees",
            "SELECT 1; DELETE FROM employees", "INSERT INTO employees(emp_no) VALUES ('z')",
            "SELECT hashed_password FROM users", "SELECT * FROM settings", "SELECT data FROM backups", "WITH x AS (DELETE FROM employees RETURNING *) SELECT * FROM x",
            "SELECT * INTO newt FROM employees", "PRAGMA query_only = OFF"]:
    t, e = call("query", {"sql": bad})
    ck(f"refused: {bad[:40]}", e, t)
db = SessionLocal()
ck("employees untouched", db.query(models.Employee).filter(models.Employee.emp_no == "T-1").first().name == "TEST ONE")
db.close()
t, e = call("query", {"sql": "SELECT no_such_col FROM employees"})
ck("a bad query says why, briefly", e and "Query failed" in t and len(t) < 340, t)
t, e = call("query", {"sql": "SELECT emp_no FROM employees", "limit": 1})
ck("row cap is respected and says so", "more exist" in t or "(1 row)" in t, t)
t, e = call("query", {"sql": "SELECT name FROM employees WHERE name LIKE '%delete%'"})
ck("a word inside quotes is not mistaken for a command", not e, t)

t, e = call("report", {"sql": "SELECT emp_no, name, total_salary FROM employees", "title": "Salaries", "format": "excel"})
ck("report returns a link, not rows", "/reports/ask/file/" in t and "TEST ONE" not in t and not e, t)
f = "/" + t.split("://", 1)[1].split("/", 1)[1].split()[0]
r = c.get(f)
ck("the file downloads", r.status_code == 200 and r.content[:2] == b"PK", (r.status_code, r.content[:20]))
t, e = call("report", {"sql": "SELECT emp_no, name FROM employees", "title": "List", "format": "pdf"})
f = "/" + t.split("://", 1)[1].split("/", 1)[1].split()[0]
ck("pdf too", c.get(f).content[:4] == b"%PDF")
ck("an invented file name is 404", c.get("/reports/ask/file/AAAAAAAAAAAAAAAAAAAA.pdf").status_code == 404)

db = SessionLocal()
ck("questions are logged", db.query(models.AuditLog).filter(models.AuditLog.action == "agent_query").count() >= 3)
db.close()
url2 = c.post("/settings/agent", headers=B, json={"origin": "https://app.infinia.ae"}).json()["url"]
ck("the link uses the address the browser was on", url2.startswith("https://app.infinia.ae/reports/ask/mcp/"), url2)
ck("a new link stops the old one", rpc("tools/list").status_code == 404)
c.delete("/settings/agent", headers=B)
p2 = "/" + url2.split("://", 1)[1].split("/", 1)[1]
ck("turned off: link refused", rpc("tools/list", p=p2).status_code == 404)

print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED: {FAIL}")
