"""portal/help/heads.js from heads_est.json + heads_app.json (the (i) notes on headings and labels)."""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = {}
for f in ("heads_app.json", "heads_est.json"):
    p = os.path.join(ROOT, "portal", "help", f)
    if os.path.exists(p):
        for k, v in json.load(open(p, encoding="utf-8")).items():
            k = " ".join(k.lower().split()).rstrip("*:").strip()
            if k and v:
                out[k] = v.strip()
with open(os.path.join(ROOT, "portal", "help", "heads.js"), "w", encoding="utf-8") as w:
    w.write("/* The (i) on every column heading and form label: \"heading\" or \"<screen>|heading\" -> note.\n"
            "   Made by deploy/merge_heads.py from heads_app.json and heads_est.json - edit those. */\n")
    w.write("window.HEAD_TIPS = " + json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True) + ";\n")
print(len(out), "notes")
