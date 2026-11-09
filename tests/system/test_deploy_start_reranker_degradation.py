"""deploy/start.sh 的 Reranker 失败路径必须显式降级（任务 M 步骤 2）。

用临时部署骨架 + stub 替身运行真实 start.sh，断言传给 uvicorn 的
RERANKER_ENABLED / RERANKER_BASE_URL；不依赖真实模型、端口或后台进程。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import textwrap
from pathlib import Path

import pytest

REAL_START_SH = Path(__file__).resolve().parents[2] / "deploy" / "start.sh"


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path
    (root / "deploy" / "reranker" / ".runtime").mkdir(parents=True)
    shutil.copy2(REAL_START_SH, root / "deploy" / "start.sh")
    (root / "deploy" / "start.sh").chmod(0o755)
    _write_executable(
        root / ".venv" / "bin" / "uvicorn",
        "#!/usr/bin/env bash\n"
        "printf 'UVICORN_ENV RERANKER_ENABLED=%s RERANKER_BASE_URL=%s\\n' "
        '"${RERANKER_ENABLED-<unset>}" "${RERANKER_BASE_URL-<unset>}"\n',
    )
    return root


def _run(root: Path, reranker_body: str, *, enabled: str = "true", runtime_env: str | None = None):
    marker = root / "deploy" / "reranker" / ".runtime" / "called.marker"
    _write_executable(root / "deploy" / "reranker" / "start.sh", reranker_body)
    if runtime_env is not None:
        (root / "deploy" / "reranker" / ".runtime" / "runtime.env").write_text(
            runtime_env, encoding="utf-8"
        )
    env = dict(os.environ)
    for key in ("RERANKER_BASE_URL", "RERANKER_SERVER_BIN", "RERANKER_MODEL_PATH"):
        env.pop(key, None)
    env["RERANKER_ENABLED"] = enabled
    env["PORT"] = str(_free_port())
    env["RA_FD_SOFT_LIMIT"] = "4096"
    result = subprocess.run(
        ["bash", str(root / "deploy" / "start.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result, marker


def _failed_stub(marker: Path) -> str:
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        printf 'called\\n' > '{marker}'
        echo 'Reranker 模型不存在：/nonexistent/model.gguf' >&2
        exit 1
        """)


def test_reranker_start_failure_disables_reranker_for_fastapi(sandbox):
    marker = sandbox / "deploy" / "reranker" / ".runtime" / "called.marker"
    result, marker = _run(sandbox, _failed_stub(marker))

    assert result.returncode == 0, result.stderr
    assert marker.exists(), "子脚本应被调用"
    assert "RRF 降级" in result.stderr
    assert "UVICORN_ENV RERANKER_ENABLED=false" in result.stdout
    assert "UVICORN_ENV RERANKER_ENABLED=true" not in result.stdout


def test_explicit_disable_keeps_existing_behavior(sandbox):
    marker = sandbox / "deploy" / "reranker" / ".runtime" / "called.marker"
    result, marker = _run(sandbox, _failed_stub(marker), enabled="false")

    assert result.returncode == 0, result.stderr
    assert "Reranker 已禁用，跳过启动与质量探针。" in result.stdout
    assert not marker.exists(), "显式禁用时不应调用 reranker/start.sh"
    assert "UVICORN_ENV RERANKER_ENABLED=false" in result.stdout


def test_successful_reranker_start_keeps_enabled(sandbox):
    runtime = sandbox / "deploy" / "reranker" / ".runtime" / "runtime.env"
    marker = sandbox / "deploy" / "reranker" / ".runtime" / "called.marker"
    body = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        printf 'called\\n' > '{marker}'
        printf 'RERANKER_BASE_URL=http://127.0.0.1:11435\\n' > '{runtime}'
        echo 'Reranker 已启动'
        exit 0
        """)
    result, _ = _run(sandbox, body)

    assert result.returncode == 0, result.stderr
    assert "使用 Reranker：http://127.0.0.1:11435" in result.stdout
    assert (
        "UVICORN_ENV RERANKER_ENABLED=true RERANKER_BASE_URL=http://127.0.0.1:11435"
        in result.stdout
    )


def test_invalid_runtime_url_disables_reranker(sandbox):
    marker = sandbox / "deploy" / "reranker" / ".runtime" / "called.marker"
    body = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        printf 'called\\n' > '{marker}'
        echo 'Reranker 已启动（无有效 runtime url）'
        exit 0
        """)
    result, _ = _run(sandbox, body, runtime_env="RERANKER_BASE_URL=http://example.com:11435\n")

    assert result.returncode == 0, result.stderr
    assert "降级启动" in result.stderr
    assert "UVICORN_ENV RERANKER_ENABLED=false" in result.stdout


def _write_failing_stop(root: Path) -> Path:
    """stop.sh stub：留下调用标记，并以非零退出码模拟 PID 校验失败。"""
    stop_marker = root / "deploy" / "reranker" / ".runtime" / "stop.marker"
    _write_executable(
        root / "deploy" / "reranker" / "stop.sh",
        textwrap.dedent(f"""\
            #!/usr/bin/env bash
            printf 'stop called\\n' > '{stop_marker}'
            echo 'stop.sh: PID 校验失败，拒绝终止' >&2
            exit 1
            """),
    )
    return stop_marker


def test_start_failure_branch_calls_stop_and_warns_on_cleanup_failure(sandbox):
    """LOW-7：子脚本失败分支必须调用 stop.sh，且清理失败不得被 || true 静默吞掉。"""
    marker = sandbox / "deploy" / "reranker" / ".runtime" / "called.marker"
    stop_marker = _write_failing_stop(sandbox)
    result, _ = _run(sandbox, _failed_stub(marker))

    assert result.returncode == 0, result.stderr
    assert stop_marker.exists(), "失败分支必须调用 stop.sh 清理"
    assert "Reranker 清理失败" in result.stderr, "stop.sh 非零退出码不得被静默吞掉"
    assert "UVICORN_ENV RERANKER_ENABLED=false" in result.stdout


def test_invalid_url_branch_calls_stop_and_warns_on_cleanup_failure(sandbox):
    """LOW-7：runtime URL 无效分支同样会留下孤立 llama-server，必须清理并告警。"""
    marker = sandbox / "deploy" / "reranker" / ".runtime" / "called.marker"
    stop_marker = _write_failing_stop(sandbox)
    body = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        printf 'called\\n' > '{marker}'
        echo 'Reranker 已启动（无有效 runtime url）'
        exit 0
        """)
    result, _ = _run(sandbox, body, runtime_env="RERANKER_BASE_URL=http://example.com:11435\n")

    assert result.returncode == 0, result.stderr
    assert stop_marker.exists(), "runtime URL 无效分支必须调用 stop.sh 清理"
    assert "Reranker 清理失败" in result.stderr, "stop.sh 非零退出码不得被静默吞掉"
    assert "UVICORN_ENV RERANKER_ENABLED=false" in result.stdout
