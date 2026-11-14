# Working on the Infinia app

Live system (app.infinia.ae) used every day - no regressions. Praveen deploys with
`cd ~/infinia-labour-tool && git pull && sudo systemctl reload-or-restart infinia`
(reload = no gap for users, deploy/install-zero-gap.sh; the app runs with a 2.5 GB memory cap - never load all backups
or other whole-data copies at once, especially at start: that froze the server 14/11/2026).

## Before every push
1. `python3 deploy/build_temporary_pages.py` if app-classic.html changed (app.html is built from it).
2. Add or extend a test in tests/ for what changed - with data shaped like the live data (long text, renamed lines,
   several sites, empty values, old records), not only the happy path.
3. Run only the tests for the area changed, e.g. `python3 tests/run_all.py lpo` or `python3 tests/run_all.py cash`
   (about 1 minute). Do not run the full set locally (~20 min on this machine): GitHub runs all of it on every
   push (.github/workflows/tests.yml). tests/known_failing.txt lists the few that may fail; it only gets shorter.
4. Reviewer agent (.claude/agents/reviewer.md) only for changes to money, payroll, cash totals, stock, database
   columns or one-time data fixes - fix what it finds before pushing.
5. Push, then reply straight away - do not wait for GitHub's run. Check it at the start of the next task
   (`gh run list -L 1`) and fix it first if red. Target: a normal change done in 2-4 minutes.
6. Tell Praveen: not working -> corrected -> result, and the deploy command (reload-or-restart).

## Stage, then live
The test copy at https://app.infinia.ae:8443 (deploy/install-staging.sh) follows GitHub main by itself within two
minutes of a push and holds last night's copy of the live data (refreshed 4:00 AM Dubai, or by hand with
`sudo bash ~/infinia-labour-tool/deploy/staging_refresh.sh`). It sends no email, push or Zoho. Check a change there
first; live only changes when Praveen runs the deploy command.

## House rules
UI standard: project doc claude/ui-standard.md. Never hard-code people's names; say "rental", not "hire";
dates DD/MM/YYYY; show figures for approval before numbers change; questions as click-answers.
