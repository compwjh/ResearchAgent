---
name: usenix-paper-assistant
description: Use this skill when a user needs to search or download USENIX Security papers through the running local ResearchAgent service.
---

# USENIX paper assistant

Use the local ResearchAgent API as the only execution boundary. Do not scrape
USENIX, download PDFs directly, or invent a detail-page URL. The scripts in
this skill call only `http://127.0.0.1:8000` and accept paper identifiers that
the search API returned.

## Search

Run:

```bash
python .codebuddy/skills/usenix-paper-assistant/scripts/search_papers.py \
  --query "agent security" --years 2024 --limit 10
```

The script creates an asynchronous USENIX Security search, waits until the
server freezes its result snapshot, and prints `candidate_id`, `search_id`,
title, year, official detail URL, and abstract status. Keep the printed
`search_id` and `candidate_id` for the import step.

## Download and import

Run with identifiers copied from a search result:

```bash
python .codebuddy/skills/usenix-paper-assistant/scripts/download_paper.py \
  --search-id SEARCH_ID --candidate-id CANDIDATE_ID
```

The product resolves the candidate from its server-owned snapshot and applies
its existing download, allowlist, identity, and knowledge-base import rules.
This skill never accepts a client-supplied URL.

## Service availability

If the local service is not running, report the Chinese error emitted by the
script and tell the user to start it with `./deploy/start.sh` (or
`./deploy/start.sh -d`). Do not claim that a search or import succeeded unless
the API returned a successful response. HTTP error bodies are reported as
service errors without exposing a Python traceback.
