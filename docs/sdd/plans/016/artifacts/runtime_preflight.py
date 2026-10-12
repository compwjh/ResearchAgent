import json, os, sqlite3, subprocess, sys, tempfile, time
from pathlib import Path

checks = []
def check(name, ok, evidence):
    checks.append({"name": name, "pass": bool(ok), "evidence": evidence})
    if not ok:
        raise AssertionError(name + ": " + str(evidence))
def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
def claim(db, owner, due, ttl=300):
    time.sleep(max(0.0, due - time.time()))
    c = sqlite3.connect(db, timeout=5)
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("BEGIN IMMEDIATE")
    row = c.execute("SELECT owner, expires FROM leases WHERE task_id='T-1' AND active=1").fetchone()
    if row and row[1] > time.time():
        c.rollback(); print(json.dumps({"status":"rejected","owner":owner})); return
    c.execute("UPDATE leases SET active=0 WHERE task_id='T-1' AND active=1")
    c.execute("INSERT INTO leases(task_id,owner,expires,active) VALUES('T-1',?,?,1)", (owner,time.time()+ttl))
    c.commit(); print(json.dumps({"status":"claimed","owner":owner}))
if len(sys.argv) > 1 and sys.argv[1] == "claim":
    claim(sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5])); raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix="spec016-") as td:
    root = Path(td); db = root / "ledger.sqlite"
    c = sqlite3.connect(db)
    mode = c.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    c.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,status TEXT,depends TEXT)")
    c.execute("CREATE TABLE leases(task_id TEXT,owner TEXT,expires REAL,active INTEGER)")
    c.execute("CREATE UNIQUE INDEX one_active_lease ON leases(task_id) WHERE active=1")
    c.commit(); c.close()
    check("sqlite_wal", mode.lower()=="wal", mode)
    due = time.time()+0.5
    ps = [subprocess.Popen([sys.executable,__file__,"claim",str(db),f"worker{i}",str(due),"300"],stdout=subprocess.PIPE,text=True) for i in range(2)]
    results = [json.loads(p.communicate(timeout=10)[0]) for p in ps]
    statuses = sorted(x["status"] for x in results)
    check("concurrent_single_claim", statuses==["claimed","rejected"], results)
    c = sqlite3.connect(db); c.execute("BEGIN IMMEDIATE")
    try:
        c.execute("INSERT INTO leases VALUES('T-1','intruder',?,1)",(time.time()+300,))
        unique_ok = False
    except sqlite3.IntegrityError:
        unique_ok = True
    c.rollback(); check("unique_active_lease", unique_ok, "duplicate active insert rejected")
    c.execute("UPDATE leases SET expires=0 WHERE active=1"); c.commit(); c.close()
    p = subprocess.run([sys.executable,__file__,"claim",str(db),"after-expiry",str(time.time()),"300"],capture_output=True,text=True,timeout=10)
    check("expired_lease_reclaim", p.returncode==0 and json.loads(p.stdout)["status"]=="claimed", p.stdout.strip())

    docs = root/"docs"; docs.mkdir()
    (docs/"task-a.md").write_text("id: A\nstatus: ready\ndepends_on: B\n")
    (docs/"task-b.md").write_text("id: B\nstatus: done\ndepends_on: -\n")
    (docs/"run-1.md").write_text("run_id: R1\ntask_id: A\nresult: ok\n")
    db.unlink()
    c = sqlite3.connect(db); c.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,status TEXT,depends TEXT)"); c.execute("CREATE TABLE runs(id TEXT PRIMARY KEY,task_id TEXT,result TEXT)")
    for f in docs.glob("task-*.md"):
        d = dict(line.split(": ",1) for line in f.read_text().splitlines())
        c.execute("INSERT INTO tasks VALUES(?,?,?)",(d["id"],d["status"],d["depends_on"]))
    d = dict(line.split(": ",1) for line in (docs/"run-1.md").read_text().splitlines())
    c.execute("INSERT INTO runs VALUES(?,?,?)",(d["run_id"],d["task_id"],d["result"])); c.commit()
    restored = c.execute("SELECT id,status,depends FROM tasks ORDER BY id").fetchall()
    run = c.execute("SELECT id,task_id,result FROM runs").fetchone(); c.close()
    check("markdown_rebuild", restored==[("A","ready","B"),("B","done","-")] and run==("R1","A","ok"), {"tasks":restored,"run":run})

    repo=root/"repo"; repo.mkdir(); git(repo,"init","-q"); git(repo,"config","user.email","preflight@example.invalid"); git(repo,"config","user.name","preflight")
    (repo/".gitignore").write_text(".worktrees/\n.sdd/runtime/\n"); (repo/"tracked.txt").write_text("base\n")
    git(repo,"add","."); git(repo,"commit","-qm","fixture"); (repo/"dirty.txt").write_text("preserve me\n")
    target=repo/".worktrees"/"spec-016"; target.parent.mkdir()
    git(repo,"worktree","add","-q","-b","preflight-spec-016",str(target),"HEAD")
    common_main=Path(git(repo,"rev-parse","--path-format=absolute","--git-common-dir")).resolve()
    common_wt=Path(git(target,"rev-parse","--path-format=absolute","--git-common-dir")).resolve()
    runtime_main=(common_main.parent/".sdd"/"runtime").resolve(); runtime_wt=(common_wt.parent/".sdd"/"runtime").resolve()
    check("shared_common_runtime",common_main==common_wt and runtime_main==runtime_wt,{"common":str(common_main),"worktree_common":str(common_wt),"runtime":str(runtime_wt)})
    check("dirty_tree_preserved",(repo/"dirty.txt").read_text()=="preserve me\n" and git(repo,"check-ignore",".worktrees/spec-016/x")==".worktrees/spec-016/x" and git(repo,"check-ignore",".sdd/runtime/x")==".sdd/runtime/x","dirty file intact; both runtime paths ignored")

print(json.dumps({"checks":checks,"passed":len([x for x in checks if x["pass"]]),"failed":len([x for x in checks if not x["pass"]])},indent=2))
