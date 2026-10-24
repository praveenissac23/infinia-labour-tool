#!/bin/bash
# Browser tests in parallel lanes: each lane has its own server ports and its own copy of the tests with the
# address rewritten (the tests name 127.0.0.1:8032).   tests/run_js_part.sh <lane 1..4> <base.db> <test files...>
cd "$(dirname "$0")/.."
LANE=$1; BASE=$2; shift 2
P=$((8060 + LANE * 10)); A=$((P + 1))
DIR=tests_lane$LANE; rm -rf $DIR; mkdir -p $DIR
for f in tests/*; do [ -f "$f" ] && sed "s/127\.0\.0\.1:8032/127.0.0.1:$P/g; s/localhost:8032/localhost:$P/g" "$f" > "$DIR/$(basename $f)"; done
OUT=${OUT:-/tmp/claude-0/runall}; mkdir -p $OUT /tmp/claude-0/shots; S=$OUT/lane$LANE.txt; : > $S
stop() { fuser -k $P/tcp $A/tcp >/dev/null 2>&1; sleep 1; }
for t in "$@"; do
  n=$(basename $t)
  stop; cp $BASE /tmp/lane$LANE.db
  (DATABASE_URL=sqlite:////tmp/lane$LANE.db INFINIA_NO_SCHED=1 SRV_MAX_BODY=${SRV_MAX_BODY:-0} SRV_PORT=$P SRV_API_PORT=$A setsid nohup python3 tests/serve_like_nginx.py > $OUT/srv_lane$LANE.log 2>&1 &)
  for i in $(seq 1 60); do curl -s -o /dev/null http://127.0.0.1:$P/health && break; sleep 1; done; sleep 1
  BASE_URL=http://127.0.0.1:$P BASE=http://127.0.0.1:$P NODE_OPTIONS="--require $PWD/tests/_relogin_shim.js" timeout 900 node $DIR/$n > $OUT/$n.log 2>&1; rc=$?
  echo "$rc $n $(tail -1 $OUT/$n.log | cut -c1-150)" >> $S
done
stop; rm -rf $DIR
echo DONE >> $S
