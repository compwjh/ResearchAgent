"""Serve ownerless read-only Task result and metrics queries."""

import json
from contextlib import closing
from pathlib import Path
from typing import Any, Dict

from .metrics import export_metrics
from .result_query import result_for_run
from .store import connect


def result_from_cli(database: Path, run_id: str) -> Dict[str, Any]:
    with closing(connect(database)) as conn:
        return result_for_run(conn, run_id)


def metrics_from_cli(database: Path, format: str) -> Dict[str, Any]:
    with closing(connect(database)) as conn:
        output = export_metrics(conn, filters={}, format=format)
    if format == "json":
        return json.loads(output)
    return {"format": "csv", "content": output}
