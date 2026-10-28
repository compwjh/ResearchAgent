#!/bin/bash
set -eu
ROOT=/private/tmp/spec043-task11-final-backend-20261028
WORKTREE=/Users/wjh/.codex/worktrees/map-usability/ResearchAgent
PYTHON=/Users/wjh/ResearchAgent/.venv/bin/python
MODE=${1:?use e2e-skip or full}
COMMON_ENV=(
  "PATH=/Users/wjh/ResearchAgent/.venv/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  "HOME=$ROOT/exit0/home"
  "TMPDIR=$ROOT/exit0/tmp"
  "XDG_CACHE_HOME=$ROOT/exit0/cache"
  "XDG_CONFIG_HOME=$ROOT/exit0/config"
  "XDG_DATA_HOME=$ROOT/exit0/data/xdg"
  "PYTHONPYCACHEPREFIX=$ROOT/exit0/pycache"
  "PYTHONNOUSERSITE=1"
  "PYTHON_DOTENV_DISABLED=1"
  "PYTHONPATH=$ROOT/plugins:$WORKTREE"
  "PYTEST_ADDOPTS="
  "LANG=C.UTF-8"
  "TZ=Asia/Shanghai"
  "NO_PROXY=127.0.0.1,localhost,::1"
  "HTTP_PROXY="
  "HTTPS_PROXY="
  "ALL_PROXY="
  "PAPER_DISCOVERY_ENABLED=true"
  "LANGFUSE_ENABLED=false"
  "LANGFUSE_PUBLIC_KEY="
  "LANGFUSE_SECRET_KEY="
  "LANGFUSE_HOST=http://127.0.0.1:9"
  "OLLAMA_BASE_URL=http://127.0.0.1:9"
  "EMBED_BASE_URL=http://127.0.0.1:9"
  "EMBED_API_KEY="
  "RERANKER_BASE_URL=http://127.0.0.1:9"
  "ONLINE_MODELS="
  "OPENAI_API_KEY="
  "ANTHROPIC_API_KEY="
  "DEEPSEEK_API_KEY="
  "DASHSCOPE_API_KEY="
  "QWEN_API_KEY="
  "GEMINI_API_KEY="
  "GOOGLE_API_KEY="
  "COHERE_API_KEY="
  "MISTRAL_API_KEY="
  "SEMANTIC_SCHOLAR_API_KEY="
  "E2E_BASE_URL=http://127.0.0.1:9"
  "LITERATURE_MAP_DB_PATH=$ROOT/exit0/data/literature-maps.sqlite3"
  "MEMORY_DB_PATH=$ROOT/exit0/data/memory.sqlite3"
  "PAPER_DISCOVERY_DB_PATH=$ROOT/exit0/data/paper-discovery.sqlite3"
  "RESEARCH_DB_PATH=$ROOT/exit0/data/research.sqlite3"
  "AGENT_TASKS_DB=$ROOT/exit0/data/agent-tasks.sqlite3"
  "KB_DIR=$ROOT/exit0/data/kb"
  "KB_META_PATH=$ROOT/exit0/data/kb/papers.json"
  "QDRANT_PATH=$ROOT/exit0/data/kb/qdrant"
  "ARTICLE_DOWNLOAD_DIR=$ROOT/exit0/data/articles"
  "PAPER_DISCOVERY_BROWSER_PROFILE_DIR=$ROOT/exit0/data/browser-profile"
)
case "$MODE" in
  e2e-skip)
    LOG="$ROOT/exit0/logs/e2e-skip.log"
    EXIT="$ROOT/exit0/logs/e2e-skip.exit"
    ARGS=( -m pytest -q -rs tests/e2e/test_research_lifecycle_e2e.py -p no:cacheprovider -p offline_isolation --basetemp="$ROOT/exit0/basetemp-e2e-skip" )
    ;;
  full)
    LOG="$ROOT/exit0/logs/pytest-full.log"
    EXIT="$ROOT/exit0/logs/pytest-full.exit"
    ARGS=( -m pytest -q tests --ignore=tests/frontend -p no:cacheprovider -p offline_isolation --basetemp="$ROOT/exit0/basetemp-final" --cov=backend --cov-report=term-missing:skip-covered --cov-report="xml:$ROOT/exit0/coverage.xml" --cov-fail-under=80 )
    COMMON_ENV+=("COVERAGE_FILE=$ROOT/exit0/.coverage")
    ;;
  ollama-skip)
    LOG="$ROOT/exit0/logs/ollama-skip.log"
    EXIT="$ROOT/exit0/logs/ollama-skip.exit"
    ARGS=( -m pytest -q -rs 'tests/research/test_ollama_direct.py::RealStreamCallTests::test_real_stream_yields_tokens_and_returns_result' -p no:cacheprovider -p offline_isolation --basetemp="$ROOT/exit0/basetemp-ollama-skip" )
    ;;
  *)
    printf 'unknown mode: %s\n' "$MODE" >&2
    exit 2
    ;;
esac
env -i "${COMMON_ENV[@]}" "$PYTHON" -c 'import os; assert "RUN_E2E" not in os.environ; assert os.environ.get("PAPER_DISCOVERY_ENABLED") == "true"; assert os.environ.get("LANGFUSE_ENABLED") == "false"; assert not os.environ.get("SEMANTIC_SCHOLAR_API_KEY"); assert not os.environ.get("OPENAI_API_KEY"); assert not os.environ.get("ONLINE_MODELS")'
printf 'RUN_E2E=absent; discovery=true; online/LLM/S2 credentials empty; dotenv disabled; Langfuse off\n' >"$ROOT/exit0/logs/env-preflight.txt"
set +e
env -i "${COMMON_ENV[@]}" "$PYTHON" "${ARGS[@]}" >"$LOG" 2>&1
STATUS=$?
set -e
printf '%s\n' "$STATUS" >"$EXIT"
printf 'mode=%s exit=%s log=%s\n' "$MODE" "$STATUS" "$LOG"
tail -n 24 "$LOG"
exit "$STATUS"
