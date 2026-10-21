import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs/sdd/plans/018/artifacts/task-04/upload-closure-matrix.json"


def _module_path(module_name: str) -> Path:
    return ROOT / (module_name.replace(".", "/") + ".py")


def test_frozen_inventory_lists_every_closure_entry_symbol():
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    retired_by_module = {
        "routes_kb": {"_submit_index_task"},
        "application": {"backfill_chunker_defaults", "mark_interrupted_on_startup", "mark_interrupted_tasks"},
    }
    modules = {
        "routes_kb": "backend.app.api.routes_kb",
        "routes_paper": "backend.app.api.routes_paper",
        "main": "backend.app.main",
        "application": "backend.app.knowledge_base.application",
        "paper_import": "backend.app.paper_discovery.application.paper_import",
        "store": "backend.app.knowledge_base.infrastructure.store",
        "index": "backend.app.knowledge_base.infrastructure.index",
        "tasks": "backend.app.knowledge_base.infrastructure.tasks",
    }
    for entry in matrix["entries"]:
        route = entry["route_or_symbol"]
        for module_name, symbol in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", route):
            if module_name not in modules:
                continue
            source = _module_path(modules[module_name]).read_text(encoding="utf-8")
            if symbol in retired_by_module.get(module_name, set()):
                assert symbol not in source, (entry["entry_id"], module_name, symbol)
            else:
                assert symbol in source, (entry["entry_id"], module_name, symbol)


def test_inventory_hashes_are_stable_and_write_entrypoints_are_registered():
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    registered = set()
    for entry in matrix["entries"]:
        route = entry["route_or_symbol"]
        registered.update(symbol for _module, symbol in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)", route))
    # The matrix is intentionally the registry for write-capable symbols; this
    # allowlist covers read-only or compatibility helpers in frozen modules.
    allowed = {
        "_document_error", "_document_summary", "_normalized_upload_content_type", "_decode_cursor", "_encode_cursor", "_encode_inspection_cursor",
        "_decode_inspection_cursor", "_canonical_document", "_generation_store", "_require_generation",
        "list_documents", "upload_document", "_read_document_source_response", "read_document_source_route",
        "head_document_source_route", "inspect_document", "reindex_document_route", "delete_document_route",
        "kb_component_status", "kb_health", "list_kb_papers", "kb_ask", "generate", "lifespan", "index",
        "handle_request_validation_error", "_fsync_directory", "_write_source_exclusive", "_snapshot_value",
        "_identity_parts", "_same_identity", "_port_status", "_index_succeeded", "_index_error_detail", "_call_supported",
        # Pure index-state helpers: field normalization/checking only; no IO,
        # metadata writes, manifest writes, or generation-marker publication.
        "_normalize_index_error", "_canonical_index_record",
        "create_paper_import_port", "create_source_reader", "read_document_source", "create_manifest_store",
        "record_id", "default_chunkers", "default_chunker_state", "ensure_dirs", "load_papers", "load_papers_strict",
        "get_paper", "resolve_paper_path", "copy_source_exclusive", "new_record", "ensure_chunkers", "get_chunker_state",
        "update_chunker_state", "point_id", "count_points", "get_client", "reset_client", "ensure_collection",
        "upsert_chunks", "_report", "_parser", "main", "__init__", "to_dict", "_safe_browser_error_message",
        "_safe_import_error_message", "_paper_import_error_response", "_paper_import_result_payload", "_paper_batch_error_response",
        "_paper_batch_payload", "_paper_batch_status_payload", "_paper_search_expired", "_paper_server_snapshot", "_paper_snapshot_for_item",
            "safe_import_error_message", "safe_import_error_code", "_import_lifecycle_boundary", "create_uploaded_document", "_capture_import_generation",
            "submit_document_reindex", "delete_document", "_default_deleter", "delete_paper_conference",
        "create_paper_import_batch", "get_paper_import_batch", "list_paper_import_batches", "iter_failed_chunkers",
        "is_chunker_auto_requeued", "_save_associations",
    }
    frozen_items = list(matrix["inventory_files"])
    frozen = {item["path"] for item in frozen_items}
    actual_hashes = {}
    for item in frozen_items:
        path = ROOT / item["path"]
        assert path.is_file(), item["path"]
        actual_hashes[item["path"]] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual_hashes[item["path"]] == item["sha256"], item["path"]
    digest_lines = "\n".join(
        f"{digest}  {path}" for path, digest in sorted(actual_hashes.items(), key=lambda item: item[1])
    ) + "\n"
    assert hashlib.sha256(digest_lines.encode("utf-8")).hexdigest() == matrix["inventory_digest"]
    for relative in frozen:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name
            if any(token in name.lower() for token in ("upload", "save", "upsert", "index", "delete", "reindex", "import", "startup", "task")):
                assert name in registered or name in allowed, (relative, name)
    # A frozen inventory must also prove that callers cannot reach legacy
    # write helpers through a direct import or a health/import side path.
    application_tree = ast.parse((ROOT / "backend/app/knowledge_base/application.py").read_text(encoding="utf-8"))
    routes_tree = ast.parse((ROOT / "backend/app/api/routes_kb.py").read_text(encoding="utf-8"))
    retired_writes = {"upsert_paper", "remove_paper", "index_paper", "index_paper_chunker", "delete_paper", "delete_paper_chunker"}
    for tree in (application_tree, routes_tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("infrastructure.index"):
                imported = {alias.name for alias in node.names}
                assert not imported & retired_writes, sorted(imported & retired_writes)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in retired_writes, node.func.id
    route_health = next(
        node for node in ast.walk(routes_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "kb_component_status"
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"ensure_collection", "upsert_chunks", "delete_paper", "delete_paper_chunker"}
        for node in ast.walk(route_health)
    )
