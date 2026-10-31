"""Past labour cycles are never rewritten by the move to exact fils (owner, 31 Oct 2026).

    cp /tmp/claude-0/full.db /tmp/pc.db
    cd app && DATABASE_URL=sqlite:////tmp/pc.db INFINIA_NO_SCHED=1 INFINIA_NO_PUSH=1 python3 ../tests/labour_fils_past_cycles_test.py

Takes every stored salary card (and its additions / deductions) of October 2026 and earlier straight from the
database file, starts the app on it (the start-up recalculates the cards, drops empty leaver cards ...), and
checks each of those rows is byte-for-byte what it was. Then shows the November 2026 cards are to the fils."""
import os, sys, sqlite3
sys.path.insert(0, '.')
import payroll_cycle as pcyc

path = os.environ['DATABASE_URL'].split('sqlite:///', 1)[1]
FAIL = []


def ck(label, ok, info=''):
    print(('PASS ' if ok else 'FAIL ') + label + ('' if ok else f'  [{str(info)[:600]}]'))
    if not ok:
        FAIL.append(label)


def snapshot():
    c = sqlite3.connect(path)
    cards = {r[0]: r for r in c.execute('select * from employee_summaries order by id')}
    adj = {r[0]: r for r in c.execute('select * from salary_adjustments order by id')}
    c.close()
    return cards, adj


cards0, adj0 = snapshot()
c = sqlite3.connect(path)
cols = [d[1] for d in c.execute('pragma table_info(employee_summaries)')]
c.close()
MY = cols.index('month_year')
past = {i: r for i, r in cards0.items() if not pcyc.exact_fils(r[MY])}
ck('the copy has past cards to protect', len(past) > 0, len(past))

from fastapi.testclient import TestClient
import main, database, models, services
cl = TestClient(main.app)
cl.__enter__()                     # the app's start-up, exactly as a restart on the server
cards1, adj1 = snapshot()
same = [i for i, r in past.items() if cards1.get(i) == r]
diff = [(r[1], r[MY], [(cols[k], r[k], (cards1.get(i) or [None] * len(cols))[k]) for k in range(len(cols)) if r[k] != (cards1.get(i) or [None] * len(cols))[k]])
        for i, r in past.items() if cards1.get(i) != r]
by = {}
for r in past.values():
    by[r[MY]] = by.get(r[MY], 0) + 1
ck(f'every card of October 2026 and earlier byte-identical after start-up ({len(same)} of {len(past)}: '
   + ', '.join(f'{k} {v}' for k, v in sorted(by.items())) + ')', not diff, diff[:5])
past_adj_cards = set(past)
ck('their additions / deductions untouched', all(adj1.get(i) == r for i, r in adj0.items() if r[1] in past_adj_cards),
   [i for i, r in adj0.items() if r[1] in past_adj_cards and adj1.get(i) != r][:5])

# and a second start-up, as the server does after every update
main._recalculate_all_summaries(database.SessionLocal())
main.drop_leaver_cards(database.SessionLocal(), closed_too=False)
cards2, _ = snapshot()
ck('... and after the start-up sweep runs again', all(cards2.get(i) == r for i, r in past.items()))

# November 2026 on: to the fils
db = database.SessionLocal()
nov = [s for s in db.query(models.EmployeeSummary).all() if pcyc.exact_fils(s.month_year)]
frac = [s for s in nov if round(s.final_salary * 100) != round(s.final_salary * 100, 6)]
ck(f'{len(nov)} cards of November 2026 on are worked out to the fils (at most two decimals)', not frac,
   [(s.emp_no, s.final_salary) for s in frac[:5]])
whole = [s for s in nov if s.final_salary != int(s.final_salary)]
print(f'NOTE {len(whole)} of {len(nov)} November cards now carry fils, e.g. ' +
      ', '.join(f'{s.emp_no} {s.final_salary:.2f}' for s in whole[:5]))
db.close()
print(f'{len(FAIL)} FAILED' if FAIL else 'PAST CYCLES UNTOUCHED - NOVEMBER 2026 ON TO THE FILS')
sys.exit(1 if FAIL else 0)
