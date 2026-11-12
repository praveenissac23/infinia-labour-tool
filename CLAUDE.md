# Working on the Infinia app

Live system (app.infinia.ae) used every day - no regressions. Praveen deploys with
`cd ~/infinia-labour-tool && git pull && sudo systemctl restart infinia`.

## Before every push
1. `python3 deploy/build_temporary_pages.py` if app-classic.html changed (app.html is built from it).
2. Add or extend a test in tests/ for what changed - with data shaped like the live data (long text, renamed lines,
   several sites, empty values, old records), not only the happy path.
3. `python3 tests/run_all.py` - everything must pass (tests/known_failing.txt lists the few that may not, with why;
   that list only ever gets shorter). GitHub runs the same on every push (.github/workflows/tests.yml).
4. Changes to money, payroll, approvals, LPO / bill / cash totals, stock, database columns or one-time data fixes:
   ask the `reviewer` agent (.claude/agents/reviewer.md) and fix what it finds before pushing.
5. Then push, and tell Praveen: not working -> corrected -> result, and the deploy command.

## Stage, then live
The test copy at https://app.infinia.ae:8443 (deploy/install-staging.sh) follows GitHub main by itself within two
minutes of a push and holds last night's copy of the live data (refreshed 4:00 AM Dubai, or by hand with
`sudo bash ~/infinia-labour-tool/deploy/staging_refresh.sh`). It sends no email, push or Zoho. Check a change there
first; live only changes when Praveen runs the deploy command.

## House rules
UI standard: project doc claude/ui-standard.md. Never hard-code people's names; say "rental", not "hire";
dates DD/MM/YYYY; show figures for approval before numbers change; questions as click-answers.
