#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-${RERANKER_BASE_URL:-http://127.0.0.1:11435}}"
base_url="${base_url%/}"
api_model="${RERANKER_API_MODEL:-}"

case "$base_url" in
  http://127.0.0.1:*|http://localhost:*|http://\[::1\]:*) ;;
  *) printf 'reranker probe failed: base URL must use HTTP loopback\n' >&2; exit 2 ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "$script_dir/../.." && pwd)"
# 质量集只有一份：与运行期 backend/.../retrieve.py 共用 quality-probe.json。
# 复用下面已有的 Python 3 检测（本脚本本来就用它校验 JSON），不引入 jq 等新依赖。
probe_file="$script_dir/quality-probe.json"
if [[ ! -f "$probe_file" ]]; then
  printf 'reranker probe failed: shared quality probe set is missing: %s\n' "$probe_file" >&2
  exit 2
fi
if [[ -x "$project_dir/.venv/bin/python" ]]; then
  python_bin="$project_dir/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="$(command -v python3)"
else
  printf 'reranker probe failed: Python 3 is required to validate JSON\n' >&2
  exit 2
fi

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/reranker-probe.XXXXXX")"
trap 'rm -rf "$tmp_dir"' EXIT

health_status="$(curl -sS -o "$tmp_dir/health.json" -w '%{http_code}' \
  --connect-timeout 2 --max-time 60 "$base_url/health")" || {
  printf 'reranker probe failed: health request failed\n' >&2
  exit 1
}
if [[ ! "$health_status" =~ ^2[0-9][0-9]$ ]]; then
  printf 'reranker probe failed: health returned HTTP %s\n' "$health_status" >&2
  exit 1
fi

RERANKER_API_MODEL="$api_model" "$python_bin" - "$probe_file" "$tmp_dir/request.json" <<'PY'
import json
import os
import sys

def fail(message):
    print(f"reranker probe failed: {message}", file=sys.stderr)
    raise SystemExit(1)

try:
    with open(sys.argv[1], encoding="utf-8") as source:
        payload = json.load(source)
except (OSError, json.JSONDecodeError):
    fail(f"cannot read shared quality probe set: {sys.argv[1]}")

if not isinstance(payload, dict):
    fail("shared quality probe set must be a JSON object")
query = payload.get("query")
documents = payload.get("documents")
if (not isinstance(query, str) or not query.strip()
        or not isinstance(documents, list) or len(documents) != 3
        or not all(isinstance(document, str) and document for document in documents)):
    fail("shared quality probe set requires one query and exactly three documents")

api_model = os.environ.get("RERANKER_API_MODEL", "")
if api_model:
    payload["model"] = api_model
with open(sys.argv[2], "w", encoding="utf-8") as output:
    json.dump(payload, output)
PY

rerank_status="$(curl -sS -o "$tmp_dir/response.json" -w '%{http_code}' \
  --connect-timeout 2 --max-time 60 \
  -H 'Content-Type: application/json' \
  --data-binary "@$tmp_dir/request.json" "$base_url/v1/rerank")" || {
  printf 'reranker probe failed: rerank request failed\n' >&2
  exit 1
}
if [[ ! "$rerank_status" =~ ^2[0-9][0-9]$ ]]; then
  printf 'reranker probe failed: rerank returned HTTP %s\n' "$rerank_status" >&2
  exit 1
fi

"$python_bin" - "$tmp_dir/response.json" <<'PY'
import json
import math
import sys

def fail(message):
    print(f"reranker probe failed: {message}", file=sys.stderr)
    raise SystemExit(1)

try:
    with open(sys.argv[1], encoding="utf-8") as source:
        payload = json.load(source)
except (OSError, json.JSONDecodeError):
    fail("response is not valid JSON")

results = payload.get("results") if isinstance(payload, dict) else None
if not isinstance(results, list) or len(results) != 3:
    fail("results must contain exactly three items")

scores = {}
for item in results:
    if not isinstance(item, dict):
        fail("each result must be an object")
    index = item.get("index")
    score = item.get("relevance_score")
    if isinstance(index, bool) or not isinstance(index, int):
        fail("index must be a non-boolean integer")
    if index in scores or index not in {0, 1, 2}:
        fail("indices must be unique and in range")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        fail("score must be a non-boolean number")
    if not math.isfinite(score):
        fail("score must be finite")
    scores[index] = float(score)

if set(scores) != {0, 1, 2}:
    fail("indices must be complete")
if len(set(scores.values())) == 1:
    fail("all quality-probe scores are identical")
if scores[1] <= max(scores[0], scores[2]):
    fail("strongly relevant document did not rank first")

print("reranker probe passed: health ready; ranking valid")
PY
