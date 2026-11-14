"""The app must start small whatever the data holds (14/11/2026: a start-up job loaded every backup at once, the app
grew to 7.5 GB and froze the server many times a day). Four 40 MB backups in the database; the app is started in a
child process, left running 8 seconds, and its peak memory must stay under 600 MB.
    cd app && DATABASE_URL=sqlite:////tmp/sm.db python3 ../tests/startup_memory_test.py  (empty db)"""
import json, os, random, resource, string, subprocess, sys
sys.path.insert(0, '.')
import database, models
models.Base.metadata.create_all(database.engine)
db = database.SessionLocal()
rnd = random.Random(1)
for i in range(4):
    rows = [{"id": n, "name": "".join(rnd.choices(string.ascii_letters, k=380))} for n in range(100000)]
    db.add(models.Backup(trigger="manual", data=json.dumps({"tables": ["employees", "chat_messages"], "employees": rows,
                                                             "chat_messages": [{"t": "hi"}]})))
    db.commit()
db.close()
code = "import sys, time; sys.path.insert(0, '.'); import main; time.sleep(8)"
r = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, INFINIA_NO_SCHED="1", INFINIA_NO_PUSH="1", INFINIA_NO_MAIL="1"),
                   capture_output=True, text=True, timeout=300)
peak_mb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
ok = r.returncode == 0 and peak_mb < 600
print(("PASS" if ok else "FAIL") + f" app started with 160 MB of backups in the database: peak {peak_mb:.0f} MB (limit 600)")
if r.returncode:
    print("FAIL start-up error:", (r.stderr or "")[-800:])
sys.exit(0 if ok else 1)
