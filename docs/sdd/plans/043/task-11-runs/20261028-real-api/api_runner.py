import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "http://127.0.0.1:8000"
MAP_ID = "0baabeae7268429c9f7e4de8098ae1d0"
ROOT = Path(__file__).resolve().parent
LOG = ROOT / "requests.jsonl"


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_name(label):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:80]


def call(method, path, body=None, label="request"):
    started = now()
    data = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {} if data is None else {"Content-Type": "application/json"}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    status = None
    text = ""
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            status = response.status
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        status = error.code
        text = error.read().decode("utf-8", errors="replace")
    except Exception as error:
        text = json.dumps({"transport_error": type(error).__name__, "message": str(error)})
    finished = now()
    try:
        response_json = json.loads(text)
    except Exception:
        response_json = None
    record = {
        "started_at": started,
        "finished_at": finished,
        "request": {"method": method, "path": path, "body": body},
        "response": {"status": status, "body_text": text, "json": response_json},
    }
    index = sum(1 for _ in LOG.open("r", encoding="utf-8")) + 1 if LOG.exists() else 1
    out = ROOT / f"{index:03d}-{safe_name(label)}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"artifact": str(out), **record}, ensure_ascii=False, indent=2))
    return status, response_json, text


def main(args):
    if args[0] == "snapshot":
        call("GET", "/", label="health-root")
        call("GET", f"/api/literature-maps/{MAP_ID}/graph", label="graph-before")
    elif args[0] == "graph":
        call("GET", f"/api/literature-maps/{MAP_ID}/graph", label=args[1] if len(args) > 1 else "graph")
    elif args[0] == "get-path":
        path = args[1]
        call("GET", path, label=args[2] if len(args) > 2 else "public-get")
    elif args[0] == "create":
        kind, key = args[1], args[2]
        body = {"kind": kind, "node_id": "21041260a5394f42891b020128fa60fa", "pagination": {"version": 1, "page_size": 50, "max_candidates": 500}, "idempotency_key": key}
        call("POST", f"/api/literature-maps/{MAP_ID}/previews", body, f"create-{kind}")
    elif args[0] == "get-preview":
        call("GET", f"/api/literature-maps/{MAP_ID}/previews/{args[1]}", label=f"preview-{args[1]}")
    elif args[0] == "get-job":
        call("GET", f"/api/literature-maps/{MAP_ID}/jobs/{args[1]}", label=f"job-{args[1]}")
    elif args[0] == "state":
        preview_id, job_id = args[1], args[2]
        call("GET", f"/api/literature-maps/{MAP_ID}/jobs/{job_id}", label=f"job-{job_id}")
        call("GET", f"/api/literature-maps/{MAP_ID}/previews/{preview_id}", label=f"preview-{preview_id}")
    elif args[0] == "load-more":
        preview_id, revision, key = args[1], int(args[2]), args[3]
        body = {"expected_preview_revision": revision, "retry_failed": False, "idempotency_key": key}
        call("POST", f"/api/literature-maps/{MAP_ID}/previews/{preview_id}/load-more", body, f"more-{preview_id}-{key}")
    elif args[0] == "revalidate":
        p = Path(args[1])
        body = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else json.loads(args[1])
        call("POST", f"/api/literature-maps/{MAP_ID}/previews/revalidate", body, "revalidate")
    elif args[0] == "apply":
        p = Path(args[1])
        body = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else json.loads(args[1])
        call("POST", f"/api/literature-maps/{MAP_ID}/previews/batch-apply", body, "batch-apply")
    elif args[0] == "analysis":
        call("GET", f"/api/literature-maps/{MAP_ID}/analysis-queue", label="analysis-queue")
    else:
        raise SystemExit("usage: snapshot | graph [LABEL] | get-path PATH [LABEL] | create KIND KEY | get-preview ID | get-job ID | state PREVIEW JOB | load-more ID REV KEY | revalidate JSON_OR_PATH | apply JSON_OR_PATH | analysis")

if __name__ == "__main__":
    main(sys.argv[1:])
