"""Phone notifications read as a list: one item a line, five at most."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../app")
import push
bad = 0
def ck(n, ok, info=""):
    global bad; bad += 0 if ok else 1; print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"  {info!r}"))
n = {"title": "PDCs due: 3 this week · 1 next week", "detail": "old run-on text",
     "lines": ["17 Oct  ·  AED 3,360.00  ·  Al Danube", "19 Oct  ·  AED 48,596.10  ·  SEOMAA Building",
               "19 Oct  ·  AED 3,880.80  ·  Uni Mix Block", "23 Oct  ·  AED 1,000.00  ·  Fourth"]}
b = push.message_for(n)["body"]
ck("one line per cheque", b.split("\n") == ["• 17 Oct  ·  AED 3,360.00  ·  Al Danube", "• 19 Oct  ·  AED 48,596.10  ·  SEOMAA Building",
                                           "• 19 Oct  ·  AED 3,880.80  ·  Uni Mix Block", "• 23 Oct  ·  AED 1,000.00  ·  Fourth"], b)
ck("no run-on detail when lines exist", "old run-on" not in b)
many = push.body_for({"lines": [f"item {i}" for i in range(9)]}).split("\n")
ck("five shown, then + more", len(many) == 6 and many[-1] == "+ 4 more - tap to see all", many)
ck("old-style notification unchanged", push.body_for({"detail": "Test"}) == "Test")
ck("blank lines ignored", push.body_for({"lines": ["", " ", "A"]}) == "• A")
print("ALL PASS" if not bad else f"{bad} FAILURE(S)"); sys.exit(1 if bad else 0)
