#!/bin/bash
# Run every test: Python tests on a fresh database each, browser tests each against a fresh copy of the
# full database behind the nginx-like server.   tests/run_all.sh [base.db] [filter]
cd "$(dirname "$0")/.."
BASE=${1:-/tmp/full_base.db}; FILTER=${2:-.}
OUT=${OUT:-/tmp/claude-0/runall}; mkdir -p $OUT /tmp/claude-0/shots
: > $OUT/summary.txt
stop() { fuser -k 8032/tcp 8033/tcp >/dev/null 2>&1; sleep 1; }    # only this runner's ports - other servers keep running
[ -n "$SKIP_PY" ] || for t in tests/*.py; do
  n=$(basename $t); [[ $n =~ $FILTER ]] || continue
  case $n in seed_*|*fixtures*|serve_like_nginx.py|__init__.py) continue;; esac
  rm -f /tmp/rt_$n.db
  (cd app && DATABASE_URL=sqlite:////tmp/rt_$n.db INFINIA_NO_SCHED=1 timeout 900 python3 ../tests/$n > $OUT/$n.log 2>&1); rc=$?
  echo "$rc $n $(grep -vE '^Migrated|^Estimation|^Variations' $OUT/$n.log | tail -1 | cut -c1-150)" >> $OUT/summary.txt
  rm -f /tmp/rt_$n.db
done
for t in tests/*.js; do
  n=$(basename $t); [[ $n =~ $FILTER ]] || continue
  stop; cp $BASE /tmp/run_js.db
  (DATABASE_URL=sqlite:////tmp/run_js.db INFINIA_NO_SCHED=1 setsid nohup python3 tests/serve_like_nginx.py > $OUT/srv.log 2>&1 &)
  for i in $(seq 1 40); do curl -s -o /dev/null http://127.0.0.1:8032/health && break; sleep 1; done; sleep 2
  NODE_OPTIONS="--require $PWD/tests/_relogin_shim.js" timeout 900 node $t > $OUT/$n.log 2>&1; rc=$?
  echo "$rc $n $(tail -1 $OUT/$n.log | cut -c1-150)" >> $OUT/summary.txt
done
stop
echo DONE >> $OUT/summary.txt
