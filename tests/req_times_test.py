"""Where the time goes (26/11/2026): request times are added up by kind and written to the server log once an hour,
so a slow screen on the live server is known by its numbers (deploy/speed_report.sh reads the lines).

Run: python3 tests/run_all.py req_times
"""
import sys, json
sys.path.insert(0, '.')
import database, models
models.Base.metadata.create_all(database.engine)
import main
FAIL = []


def ck(l, ok, x=''):
    print(('PASS ' if ok else 'FAIL ') + l + ('' if ok else f'  [{x}]'))
    if not ok:
        FAIL.append(l)


ck('requests for different records count as one kind', main._req_shape('GET', '/store/requests/158') == main._req_shape('GET', '/store/requests/159') == 'GET /store/requests/#')
ck('...also months and codes in the path', main._req_shape('GET', '/summaries/December%202026/full-cycle') == 'GET /summaries/#/full-cycle')
main._REQ_T.clear(); main._REQ_T_AT[0] = 0.0
lines = []
out = lambda *a, **k: lines.append(a[0])
main._req_time('GET', '/store/items', 0.2, now=1000, out=out)
main._req_time('GET', '/store/items', 1.4, now=1500, out=out)
main._req_time('POST', '/store/requests/7/decision', 0.1, now=2000, out=out)
main._req_time('GET', '/health', 9, now=2100, out=out)
main._req_time('GET', '/store/chat/stream', 99, now=2200, out=out)
ck('nothing is written inside the hour', not lines and len(main._REQ_T) == 2, (lines, main._REQ_T))
main._req_time('GET', '/employees', 0.05, now=1000 + 3600, out=out)
ck('after an hour one line goes to the log', len(lines) == 1 and lines[0].startswith('TIMES '), lines)
d = json.loads(lines[0][6:])
ck('...with the totals and the heaviest first (kind, calls, average ms, longest ms, over 1 s)',
   d['calls'] == 4 and d['over1s'] == 1 and d['top'][0] == ['GET /store/items', 2, 800, 1400, 1], d)
ck('...and it starts again from nothing', not main._REQ_T)
for k in range(1000):
    main._req_time('GET', f'/x{"y" * (k % 7)}/{"abc"[k % 3]}{chr(97 + k % 26)}{chr(97 + k // 26 % 26)}', 0.01, now=5000, out=out)
ck('it never grows past 400 kinds', len(main._REQ_T) <= 400, len(main._REQ_T))
ck('a bad value never breaks a request', main._req_time('GET', None, 'x', out=out) is None)
src = open('main.py', encoding='utf-8').read()
ck('every request is timed, after the answer has gone', '_req_time(scope["method"], scope["path"], dt)' in src)
rep = open('../deploy/speed_report.sh', encoding='utf-8').read()
ck('the report only looks: no reload, no restart, nothing written under /etc', 'systemctl reload' not in rep and 'systemctl restart' not in rep and 'tee ' not in rep and ' > /etc' not in rep)
print("\nALL PASS" if not FAIL else f"\n{len(FAIL)} FAILED")
sys.exit(1 if FAIL else 0)
