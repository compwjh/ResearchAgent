"""CLI contract tests with no real judge, score transport, or network."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.eval_042 import cli


ROOT = Path(__file__).resolve().parents[2]
LEGACY_CLI = ROOT / "docs/sdd/plans/042/task-02-run-eval.py"


def _load_legacy_cli():
    spec = importlib.util.spec_from_file_location("legacy_evaluation_cli", LEGACY_CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reports(output_dir: Path):
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    assert json_path.exists()
    assert markdown_path.exists()
    return json.loads(json_path.read_text(encoding="utf-8")), markdown_path.read_text(
        encoding="utf-8"
    )


def _forbid_runner_and_post(monkeypatch):
    monkeypatch.setattr(
        cli.runner,
        "run",
        lambda *args, **kwargs: pytest.fail("invalid CLI arguments must not run evaluation"),
    )
    monkeypatch.setattr(
        cli.langfuse_export,
        "post_score",
        lambda **kwargs: pytest.fail("invalid CLI arguments must not post scores"),
    )


@pytest.mark.parametrize(
    "legacy_args",
    [
        ("--out", "--dataset"),
        ("--out", "--max-items", "2", "--dataset"),
        ("--out=--dataset",),
    ],
)
def test_legacy_out_missing_value_is_nonzero_without_runner_or_default_dataset(
    legacy_args, tmp_path, monkeypatch
):
    legacy = _load_legacy_cli()
    _forbid_runner_and_post(monkeypatch)
    output_dir = tmp_path / "legacy-invalid"
    args = [
        *legacy_args,
        str(tmp_path / "missing.json"),
        "--output-dir",
        str(output_dir),
    ]

    exit_code = legacy.main(args)

    assert exit_code == 2
    document, _ = _reports(output_dir)
    assert document["status"] == "failed"
    assert document["finished_at"]


def test_unknown_argument_does_not_echo_token_or_url_auth_and_writes_failure_reports(
    tmp_path, monkeypatch, capsys
):
    _forbid_runner_and_post(monkeypatch)
    output_dir = tmp_path / "unknown-argument"
    token = "sk-cli-secret-value"
    url_password = "url-password-secret"

    exit_code = cli.main(
        [
            "--dataset",
            str(tmp_path / "missing.json"),
            "--output-dir",
            str(output_dir),
            "--api-key",
            token,
            "--proxy",
            f"http://url-user:{url_password}@127.0.0.1:3000",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert token not in captured.out + captured.err
    assert url_password not in captured.out + captured.err
    document, markdown = _reports(output_dir)
    serialized = json.dumps(document, ensure_ascii=False) + markdown
    assert token not in serialized
    assert url_password not in serialized


@pytest.mark.parametrize(
    "arguments",
    [
        ("--dataset", "dataset.json", "--export"),
        ("--dataset", "dataset.json", "--repeats", "0"),
        ("--dataset", "dataset.json", "--max-items", "-1"),
    ],
)
def test_invalid_cli_parameters_are_nonzero_and_create_failure_reports(
    arguments, tmp_path, monkeypatch
):
    _forbid_runner_and_post(monkeypatch)
    output_dir = tmp_path / "invalid-parameters"
    exit_code = cli.main(
        [
            *arguments,
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    document, markdown = _reports(output_dir)
    assert document["status"] == "failed"
    assert document["finished_at"]
    assert "# Agent evaluation report" in markdown


def test_bad_dataset_returns_nonzero_with_json_and_markdown_reports(tmp_path, capsys):
    dataset_path = tmp_path / "bad.json"
    dataset_path.write_text("{not valid json", encoding="utf-8")
    output_dir = tmp_path / "bad-dataset"

    exit_code = cli.main(
        [
            "--dataset",
            str(dataset_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    output = json.loads(captured.out)
    assert output["exit_code"] == 1
    assert output["status"] == "failed"
    assert "report.json" in output["report_json"]
    assert "report.md" in output["report_markdown"]
    assert "evaluation failed" in captured.err
    document, markdown = _reports(output_dir)
    assert document["status"] == "failed"
    assert document["finished_at"]
    assert document["errors"]
    assert "## Errors" in markdown


def test_old_dry_run_is_rejected_without_runner_or_score_post(tmp_path, monkeypatch):
    legacy = _load_legacy_cli()
    _forbid_runner_and_post(monkeypatch)
    output_dir = tmp_path / "dry-run"

    exit_code = legacy.main(
        [
            "--dry-run",
            "--dataset",
            str(tmp_path / "missing.json"),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    document, _ = _reports(output_dir)
    assert document["status"] == "failed"


@pytest.mark.parametrize(
    "module_args",
    [
        ["-m", "backend.eval_042.cli", "--help"],
        [str(LEGACY_CLI), "--help"],
    ],
)
def test_both_cli_entrypoints_help_work_from_unrelated_cwd(tmp_path, module_args):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [sys.executable, *module_args],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--dataset" in completed.stdout
    assert "--output-dir" in completed.stdout
    assert completed.stderr == ""


def test_legacy_entrypoint_runs_from_unrelated_cwd_without_network_on_bad_dataset(
    tmp_path,
):
    dataset_path = tmp_path / "bad.json"
    dataset_path.write_text("{not valid json", encoding="utf-8")
    output_file = tmp_path / "legacy-summary.json"
    unrelated_cwd = tmp_path / "cwd"
    unrelated_cwd.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(LEGACY_CLI),
            "--dataset",
            str(dataset_path),
            "--out",
            str(output_file),
        ],
        cwd=unrelated_cwd,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()
    assert "evaluation failed" in completed.stderr
    assert "sk-secret" not in completed.stdout + completed.stderr
