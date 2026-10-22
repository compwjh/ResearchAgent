"""Canonical evaluation runner contract tests with fully fake collaborators."""
from __future__ import annotations

import json
import urllib.error

import pytest

from backend.eval_042 import runner
from backend.eval_042.report import ReportWriteError


@pytest.fixture(autouse=True)
def no_runner_sleep(monkeypatch):
    """Verification retries must be deterministic and instant."""
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)


def _item(
    trace_id: str = "trace-1",
    *,
    task: str = "chat_quality",
    output: str | None = "A complete answer.",
    status: str = "scored",
    synthetic: bool = False,
    prior_context: str | None = None,
):
    return {
        "trace_id": trace_id,
        "task": task,
        "input": "What should be evaluated?",
        "output": output,
        "status": status,
        "synthetic": synthetic,
        "prior_context": prior_context,
    }


def _artifacts(output_dir):
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    assert json_path.exists()
    assert markdown_path.exists()
    return json.loads(json_path.read_text(encoding="utf-8")), markdown_path.read_text(
        encoding="utf-8"
    )


def _fake_scored_judge(monkeypatch, *, label="good", score=1.0, calls=None):
    def judge(model, task, question, answer, repeats, *, ctx=None):
        if calls is not None:
            calls.append(
                {
                    "model": model,
                    "task": task,
                    "question": question,
                    "answer": answer,
                    "repeats": repeats,
                    "ctx": ctx,
                }
            )
        return [
            {
                "status": "scored",
                "label": label,
                "score": score,
                "explanation": "safe judge rationale",
            }
            for _ in range(repeats)
        ]

    monkeypatch.setattr(runner.judge_client, "judge_repeats", judge)


def test_runner_success_posts_once_and_verifies_exact_score_fields(
    tmp_path, monkeypatch
):
    judge_calls = []
    post_calls = []
    verify_calls = []
    _fake_scored_judge(monkeypatch, calls=judge_calls)

    def post_score(*, name, value, trace_id, comment):
        post_calls.append(
            {"name": name, "value": value, "trace_id": trace_id, "comment": comment}
        )
        return {"id": "score-new"}

    def find_score_by_id(score_id, trace_id, *, limit):
        verify_calls.append((score_id, trace_id, limit))
        return {
            "id": "score-new",
            "traceId": "trace-1",
            "name": "chat_quality",
            "value": 1.0,
        }

    monkeypatch.setattr(runner.langfuse_export, "post_score", post_score)
    monkeypatch.setattr(runner.langfuse_export, "find_score_by_id", find_score_by_id)

    output_dir = tmp_path / "success"
    result = runner.run(
        output_dir=output_dir,
        items=[_item()],
        task="chat_quality",
        primary="judge-9b",
        repeats=3,
    )

    document, markdown = _artifacts(output_dir)
    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["summary"] == {
        "scored": 1,
        "skipped": 0,
        "unavailable": 0,
        "written": 1,
        "verified": 1,
        "failed": 0,
        "no_prior_context": 0,
    }
    assert len(judge_calls) == 1
    assert judge_calls[0]["ctx"] is None
    assert len(post_calls) == 1
    assert post_calls[0]["name"] == "chat_quality"
    assert post_calls[0]["value"] == 1.0
    assert post_calls[0]["trace_id"] == "trace-1"
    assert "safe judge rationale" in post_calls[0]["comment"]
    assert verify_calls == [("score-new", "trace-1", 100)]
    item = document["items"][0]
    assert item["status"] == "scored"
    assert item["score_id"] == "score-new"
    assert item["written"] is True
    assert item["verified"] is True
    assert item["requested"] is True
    assert item["expected_value"] == 1.0
    assert item["verified_value"] == 1.0
    assert "trace-1" in markdown
    assert "score-new" in markdown
    assert "judge-9b" in markdown


def test_runner_waits_for_delayed_exact_score_visibility_with_bounded_backoff(
    tmp_path, monkeypatch
):
    _fake_scored_judge(monkeypatch)
    post_calls = []
    verify_calls = []
    sleeps = []

    def post_score(**kwargs):
        post_calls.append(kwargs)
        return {"id": "score-delayed"}

    def find_score_by_id(score_id, trace_id, *, limit):
        verify_calls.append((score_id, trace_id, limit))
        if len(verify_calls) < 3:
            return None
        return {
            "id": "score-delayed",
            "traceId": "trace-1",
            "name": "chat_quality",
            "value": 1.0,
        }

    monkeypatch.setattr(runner.time, "sleep", sleeps.append)
    monkeypatch.setattr(runner.langfuse_export, "post_score", post_score)
    monkeypatch.setattr(runner.langfuse_export, "find_score_by_id", find_score_by_id)

    result = runner.run(output_dir=tmp_path, items=[_item()])

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert len(post_calls) == 1
    assert verify_calls == [
        ("score-delayed", "trace-1", 100),
        ("score-delayed", "trace-1", 100),
        ("score-delayed", "trace-1", 100),
    ]
    assert sleeps == [1, 2]


def test_runner_permanent_exact_score_404_is_nonzero_after_finite_visibility_window(
    tmp_path, monkeypatch
):
    _fake_scored_judge(monkeypatch)
    post_calls = []
    verify_calls = []
    sleeps = []

    def post_score(**kwargs):
        post_calls.append(kwargs)
        return {"id": "score-never-visible"}

    def find_score_by_id(score_id, trace_id, *, limit):
        verify_calls.append((score_id, trace_id, limit))
        return None

    monkeypatch.setattr(runner.time, "sleep", sleeps.append)
    monkeypatch.setattr(runner.langfuse_export, "post_score", post_score)
    monkeypatch.setattr(runner.langfuse_export, "find_score_by_id", find_score_by_id)

    result = runner.run(output_dir=tmp_path, items=[_item()])
    document, markdown = _artifacts(tmp_path)

    assert runner._VERIFY_ATTEMPTS == 6
    assert runner._VERIFY_BACKOFF_SECONDS == (1, 2, 3, 4, 5)
    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert len(post_calls) == 1
    assert len(verify_calls) == 6
    assert sleeps == [1, 2, 3, 4, 5]
    item = document["items"][0]
    assert item["score_id"] == "score-never-visible"
    assert item["written"] is True
    assert item["verified"] is False
    assert item["verification_status"] == "not_found"
    assert "score id not found on trace" in json.dumps(document)
    assert "score id not found on trace" in markdown


@pytest.mark.parametrize("failure", ["unauthorized", "forbidden", "bad_json", "mismatch"])
def test_runner_score_verification_fails_fast_for_non_visibility_failures(
    failure, tmp_path, monkeypatch
):
    _fake_scored_judge(monkeypatch)
    post_calls = []
    verify_calls = []
    sleeps = []

    def post_score(**kwargs):
        post_calls.append(kwargs)
        return {"id": "score-fail-fast"}

    def find_score_by_id(score_id, trace_id, *, limit):
        verify_calls.append((score_id, trace_id, limit))
        if failure == "unauthorized":
            raise urllib.error.HTTPError(
                "http://127.0.0.1:3000/api/public/scores/score-fail-fast",
                401,
                "unauthorized",
                {},
                None,
            )
        if failure == "forbidden":
            raise urllib.error.HTTPError(
                "http://127.0.0.1:3000/api/public/scores/score-fail-fast",
                403,
                "forbidden",
                {},
                None,
            )
        if failure == "bad_json":
            raise ValueError("bad score JSON")
        return {
            "id": "old-score",
            "traceId": "trace-1",
            "name": "chat_quality",
            "value": 1.0,
        }

    monkeypatch.setattr(runner.time, "sleep", sleeps.append)
    monkeypatch.setattr(runner.langfuse_export, "post_score", post_score)
    monkeypatch.setattr(runner.langfuse_export, "find_score_by_id", find_score_by_id)

    result = runner.run(output_dir=tmp_path, items=[_item()])
    document, markdown = _artifacts(tmp_path)

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert len(post_calls) == 1
    assert len(verify_calls) == 1
    assert sleeps == []
    item = document["items"][0]
    assert item["score_id"] == "score-fail-fast"
    assert item["written"] is True
    assert item["verified"] is False
    assert item["verification_status"] in {"error", "mismatch"}
    assert "score" in json.dumps(document)
    assert "score" in markdown


def test_runner_passes_memory_context_to_judge_and_does_not_guess_it(
    tmp_path, monkeypatch
):
    calls = []
    _fake_scored_judge(
        monkeypatch,
        label="remembered",
        score=1.0,
        calls=calls,
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kwargs: {"id": "memory-score"},
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda score_id, trace_id, *, limit: {
            "id": score_id,
            "traceId": trace_id,
            "name": "memory_correctness",
            "value": 1.0,
        },
    )

    context = "User previously stated: prefers espresso."
    result = runner.run(
        output_dir=tmp_path,
        items=[
            _item(
                trace_id="memory-trace",
                task="memory_correctness",
                prior_context=context,
            )
        ],
        task="memory_correctness",
        repeats=2,
    )

    assert result["exit_code"] == 0
    assert len(calls) == 1
    assert calls[0]["ctx"] == context


def test_runner_missing_memory_context_skips_without_judge_or_post(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        runner.judge_client,
        "judge_repeats",
        lambda *args, **kwargs: pytest.fail("missing context must not call judge"),
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kwargs: pytest.fail("missing context must not post score"),
    )

    result = runner.run(
        output_dir=tmp_path,
        items=[
            _item(
                trace_id="memory-no-context",
                task="memory_correctness",
                prior_context=None,
            )
        ],
        task="memory_correctness",
    )

    document, _ = _artifacts(tmp_path)
    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["summary"]["skipped"] == 1
    assert result["summary"]["no_prior_context"] == 1
    assert document["items"][0] == {
        "trace_id": "memory-no-context",
        "task": "memory_correctness",
        "status": "skipped",
        "skip_reason": "no_prior_context",
        "synthetic": False,
    }


def test_runner_empty_output_skips_without_judge_or_post(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner.judge_client,
        "judge_repeats",
        lambda *args, **kwargs: pytest.fail("empty output must not call judge"),
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kwargs: pytest.fail("empty output must not post score"),
    )

    result = runner.run(
        output_dir=tmp_path,
        items=[_item(trace_id="blank", output="   ")],
    )

    assert result["exit_code"] == 0
    assert result["summary"]["skipped"] == 1
    assert result["document"]["items"][0]["skip_reason"] == "empty_output"


@pytest.mark.parametrize(
    "output",
    ["", "研究 Intake 已保存：这是一条分类 fixture。"],
    ids=["empty-output", "intake-output"],
)
def test_runner_prioritizes_missing_memory_context_before_output_skip(
    output, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        runner.judge_client,
        "judge_repeats",
        lambda *args, **kwargs: pytest.fail("missing memory context must skip before judge"),
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kwargs: pytest.fail("missing memory context must skip before score"),
    )

    result = runner.run(
        output_dir=tmp_path,
        items=[
            _item(
                trace_id="memory-missing-context",
                task="memory_correctness",
                output=output,
                prior_context=None,
            )
        ],
        task="memory_correctness",
    )

    document, markdown = _artifacts(tmp_path)
    assert result["exit_code"] == 0
    assert result["summary"]["skipped"] == 1
    assert result["summary"]["no_prior_context"] == 1
    assert document["items"][0]["skip_reason"] == "no_prior_context"
    assert "no_prior_context" in markdown


def test_runner_sanitizes_explanation_source_payload_but_keeps_safe_rationale(
    tmp_path, monkeypatch
):
    unsafe_markers = (
        "SOURCE_QUESTION",
        "SOURCE_ANSWER",
        "SOURCE_CONTEXT",
        "SOURCE_Q",
        "SOURCE_A",
    )
    unsafe_explanation = (
        "Question: SOURCE_QUESTION Answer: SOURCE_ANSWER "
        "ctx: SOURCE_CONTEXT q: SOURCE_Q a: SOURCE_A"
    )
    safe_explanation = "Answer is relevant and complete."
    explanations = iter((unsafe_explanation, safe_explanation))
    post_calls = []

    def fake_judge(model, task, question, answer, repeats, *, ctx=None):
        explanation = next(explanations)
        return [
            {
                "status": "scored",
                "label": "good",
                "score": 1.0,
                "explanation": explanation,
            }
            for _ in range(repeats)
        ]

    def fake_post_score(*, name, value, trace_id, comment):
        post_calls.append(comment)
        return {"id": f"score-{trace_id}"}

    def fake_find_score(score_id, trace_id, *, limit):
        return {
            "id": score_id,
            "traceId": trace_id,
            "name": "chat_quality",
            "value": 1.0,
        }

    monkeypatch.setattr(runner.judge_client, "judge_repeats", fake_judge)
    monkeypatch.setattr(runner.langfuse_export, "post_score", fake_post_score)
    monkeypatch.setattr(
        runner.langfuse_export, "find_score_by_id", fake_find_score
    )

    result = runner.run(
        output_dir=tmp_path,
        items=[
            _item(trace_id="unsafe-explanation"),
            _item(trace_id="safe-explanation"),
        ],
        task="chat_quality",
    )

    document, markdown = _artifacts(tmp_path)
    serialized = json.dumps(document, ensure_ascii=False) + markdown
    assert result["exit_code"] == 0
    assert result["summary"]["verified"] == 2
    for marker in unsafe_markers:
        assert marker not in serialized
        assert all(marker not in comment for comment in post_calls)
    assert safe_explanation in serialized
    assert any(safe_explanation in comment for comment in post_calls)


@pytest.mark.parametrize("failure_mode", ["judge_error", "explanation"])
def test_runner_redacts_question_answer_assignment_variants_from_outputs(
    failure_mode, tmp_path, monkeypatch
):
    question = "PRIVATE_ORIGINAL_QUESTION"
    answer = "PRIVATE_ORIGINAL_ANSWER"
    private_values = (
        question,
        answer,
        "PRIVATE_Q",
        "PRIVATE_A",
        "PRIVATE_CTX",
        "PRIVATE_PRIOR_CONTEXT",
        "PRIVATE_MARKER",
    )
    payload = (
        "judge failed "
        f"{question} {answer} Question={question} Answer={answer} "
        "q=PRIVATE_Q a=PRIVATE_A ctx=PRIVATE_CTX "
        "prior_context=PRIVATE_PRIOR_CONTEXT marker=PRIVATE_MARKER"
    )
    post_calls = []

    def fake_judge(model, task, received_question, received_answer, repeats, *, ctx=None):
        if failure_mode == "judge_error":
            raise RuntimeError(payload)
        return [
            {
                "status": "scored",
                "label": "good",
                "score": 1.0,
                "explanation": f"Safe rationale retained. {payload}",
            }
            for _ in range(repeats)
        ]

    monkeypatch.setattr(runner.judge_client, "judge_repeats", fake_judge)
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kwargs: (post_calls.append(kwargs["comment"]) or {"id": "safe-score"}),
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda score_id, trace_id, *, limit: {
            "id": score_id,
            "traceId": trace_id,
            "name": "chat_quality",
            "value": 1.0,
        },
    )

    item = _item()
    item["input"] = question
    item["output"] = answer
    result = runner.run(output_dir=tmp_path, items=[item], task="chat_quality")
    document, markdown = _artifacts(tmp_path)
    serialized = json.dumps(result, ensure_ascii=False) + json.dumps(
        document, ensure_ascii=False
    ) + markdown

    for private_value in private_values:
        assert private_value not in serialized
        assert all(private_value not in comment for comment in post_calls)
    if failure_mode == "judge_error":
        assert result["exit_code"] == 1
        assert post_calls == []
    else:
        assert result["exit_code"] == 0
        assert "reason_code=judge_explanation_source_echo_redacted" in serialized
        assert any(
            "reason_code=judge_explanation_source_echo_redacted" in comment
            for comment in post_calls
        )


def test_runner_checkpoints_requested_fields_before_score_post(tmp_path, monkeypatch):
    _fake_scored_judge(monkeypatch)
    observed_before_post = []
    output_dir = tmp_path / "requested-checkpoint"

    def post_score(**kwargs):
        persisted = json.loads(
            (output_dir / "report.json").read_text(encoding="utf-8")
        )
        observed_before_post.append(persisted)
        return {"id": "requested-score"}

    monkeypatch.setattr(runner.langfuse_export, "post_score", post_score)
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda score_id, trace_id, *, limit: {
            "id": score_id,
            "traceId": trace_id,
            "name": "chat_quality",
            "value": 1.0,
        },
    )

    result = runner.run(output_dir=output_dir, items=[_item()])

    assert result["exit_code"] == 0
    assert len(observed_before_post) == 1
    requested_item = observed_before_post[0]["items"][-1]
    assert requested_item["requested"] is True
    assert requested_item["expected_value"] == 1.0
    assert requested_item["verified"] is False
    assert requested_item["verified_value"] is None


@pytest.mark.parametrize("failure_type", [OSError, ReportWriteError])
def test_runner_returns_structured_failure_when_checkpoint_stays_broken(
    failure_type, tmp_path, monkeypatch
):
    error_text = "persistent checkpoint failure SOURCE_Q SOURCE_A"
    checkpoint_calls = 0
    real_checkpoint = runner.ReportWriter.checkpoint

    def fail_after_skeleton(self, document):
        nonlocal checkpoint_calls
        checkpoint_calls += 1
        if checkpoint_calls >= 2:
            raise failure_type(error_text)
        return real_checkpoint(self, document)

    monkeypatch.setattr(runner.ReportWriter, "checkpoint", fail_after_skeleton)

    output_dir = tmp_path / "checkpoint-failure"
    result = runner.run(
        output_dir=output_dir,
        items=[_item(trace_id="checkpoint-trace", output="")],
    )

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert result["report_paths"] == {
        "json": str(output_dir / "report.json"),
        "markdown": str(output_dir / "report.md"),
    }
    assert checkpoint_calls >= 2
    assert result["errors"]
    failure_text = json.dumps(result, ensure_ascii=False)
    assert "SOURCE_Q" not in failure_text
    assert "SOURCE_A" not in failure_text
    assert (output_dir / "report.json").exists()
    assert (output_dir / "report.md").exists()
    persisted = (output_dir / "report.json").read_text(encoding="utf-8")
    markdown = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "SOURCE_Q" not in persisted + markdown
    assert json.loads(persisted)["status"] != "completed"


def test_runner_partial_judge_failure_is_unavailable_and_nonzero(
    tmp_path, monkeypatch
):
    post_calls = []

    def partial_judge(*args, **kwargs):
        return [
            {
                "status": "scored",
                "label": "good",
                "score": 1.0,
                "explanation": "first completed call",
            },
            {
                "status": "unavailable",
                "label": None,
                "score": None,
                "error": "TimeoutError: judge timed out",
            },
            {
                "status": "scored",
                "label": "good",
                "score": 1.0,
                "explanation": "third call must not rescue the item",
            },
        ]

    monkeypatch.setattr(runner.judge_client, "judge_repeats", partial_judge)
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kwargs: post_calls.append(kwargs),
    )

    result = runner.run(output_dir=tmp_path, items=[_item()], repeats=3)
    document, markdown = _artifacts(tmp_path)

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert result["summary"]["unavailable"] == 1
    assert result["summary"]["failed"] == 0
    item = document["items"][0]
    assert item["status"] == "unavailable"
    assert item["score"] is None
    assert item["written"] is False
    assert item["verified"] is False
    assert post_calls == []
    assert "TimeoutError" in json.dumps(document)
    assert "judge timed out" in markdown


@pytest.mark.parametrize(
    "case",
    ["empty", "bad_json", "bad_shape", "synthetic_only"],
)
def test_runner_invalid_source_fails_with_json_and_markdown(case, tmp_path):
    output_dir = tmp_path / case
    kwargs = {"output_dir": output_dir}
    if case == "empty":
        kwargs["items"] = []
    elif case == "synthetic_only":
        kwargs["items"] = [_item(trace_id="synthetic", synthetic=True)]
    else:
        dataset_path = tmp_path / f"{case}.json"
        dataset_path.write_text(
            "{not valid json" if case == "bad_json" else '{"items": []}',
            encoding="utf-8",
        )
        kwargs["dataset_path"] = dataset_path

    result = runner.run(**kwargs)
    document, markdown = _artifacts(output_dir)

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert document["status"] == "failed"
    assert document["finished_at"]
    assert document["errors"]
    assert "## Errors" in markdown


def test_runner_post_failure_is_nonzero_and_preserves_local_report(tmp_path, monkeypatch):
    _fake_scored_judge(monkeypatch)
    verify_calls = []

    def post_failure(**kwargs):
        raise RuntimeError("score service unavailable")

    monkeypatch.setattr(runner.langfuse_export, "post_score", post_failure)
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda *args, **kwargs: verify_calls.append(True),
    )

    result = runner.run(output_dir=tmp_path, items=[_item()])
    document, markdown = _artifacts(tmp_path)

    assert result["exit_code"] == 1
    assert document["status"] == "failed"
    item = document["items"][0]
    assert item["status"] == "failed"
    assert item["written"] is False
    assert item["requested"] is True
    assert item["expected_value"] == 1.0
    assert item["verified_value"] is None
    assert "score_id" not in item
    assert verify_calls == []
    assert "score service unavailable" in json.dumps(document)
    assert "score service unavailable" in markdown


def test_runner_missing_post_score_id_is_nonzero_and_does_not_verify(
    tmp_path, monkeypatch
):
    _fake_scored_judge(monkeypatch)
    verify_calls = []
    monkeypatch.setattr(runner.langfuse_export, "post_score", lambda **kwargs: {})
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda *args, **kwargs: verify_calls.append(True),
    )

    result = runner.run(output_dir=tmp_path, items=[_item()])
    document, _ = _artifacts(tmp_path)

    assert result["exit_code"] == 1
    item = document["items"][0]
    assert item["status"] == "failed"
    assert item["written"] is False
    assert "score_id" not in item
    assert verify_calls == []
    assert "ScoreResponseError" in json.dumps(document)


@pytest.mark.parametrize(
    "returned_score",
    [
        pytest.param(
            {
                "id": "old-score",
                "traceId": "trace-1",
                "name": "chat_quality",
                "value": 1.0,
            },
            id="old-same-name-score",
        ),
        pytest.param(
            {
                "id": "score-new",
                "traceId": "wrong-trace",
                "name": "chat_quality",
                "value": 1.0,
            },
            id="trace-mismatch",
        ),
        pytest.param(
            {
                "id": "score-new",
                "traceId": "trace-1",
                "name": "wrong-task",
                "value": 1.0,
            },
            id="name-mismatch",
        ),
        pytest.param(
            {
                "id": "score-new",
                "traceId": "trace-1",
                "name": "chat_quality",
                "value": 0.5,
            },
            id="value-mismatch",
        ),
    ],
)
def test_runner_score_verification_mismatch_is_nonzero_and_retains_score_id(
    returned_score, tmp_path, monkeypatch
):
    _fake_scored_judge(monkeypatch)
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kwargs: {"id": "score-new"},
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda score_id, trace_id, *, limit: returned_score,
    )

    result = runner.run(output_dir=tmp_path, items=[_item()])
    document, markdown = _artifacts(tmp_path)

    assert result["exit_code"] == 1
    item = document["items"][0]
    assert item["status"] == "failed"
    assert item["score_id"] == "score-new"
    assert item["written"] is True
    assert item["verified"] is False
    assert item["requested"] is True
    assert item["expected_value"] == 1.0
    assert item["verified_value"] == returned_score["value"]
    assert "score field mismatch" in json.dumps(document)
    assert "score field mismatch" in markdown


def test_runner_finalizes_failed_report_after_source_exception(tmp_path, monkeypatch):
    observed = {}
    real_writer = runner.ReportWriter

    class SpyWriter(real_writer):
        def __init__(self, *args, **kwargs):
            self.events = []
            super().__init__(*args, **kwargs)
            observed["writer"] = self

        def checkpoint(self, document):
            self.events.append(
                ("checkpoint", document.get("status"), len(document.get("items", [])))
            )
            return super().checkpoint(document)

        def finish(self, status, *, errors=None):
            self.events.append(("finish", status, len(self.document.get("items", []))))
            return super().finish(status, errors=errors)

    monkeypatch.setattr(runner, "ReportWriter", SpyWriter)
    dataset_path = tmp_path / "bad.json"
    dataset_path.write_text("{not valid json", encoding="utf-8")

    result = runner.run(output_dir=tmp_path / "failure", dataset_path=dataset_path)
    writer = observed["writer"]

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert result["document"]["finished_at"]
    assert result["document"]["errors"]
    assert writer.events[0] == ("checkpoint", "running", 0)
    assert ("finish", "failed", 0) in writer.events
    assert writer.events[-1] == ("checkpoint", "failed", 0)


def test_runner_checkpoints_after_each_item_and_finalizes_report_on_success(
    tmp_path, monkeypatch
):
    _fake_scored_judge(monkeypatch)
    monkeypatch.setattr(
        runner.langfuse_export,
        "post_score",
        lambda **kwargs: {"id": "score-checkpoint"},
    )
    monkeypatch.setattr(
        runner.langfuse_export,
        "find_score_by_id",
        lambda score_id, trace_id, *, limit: {
            "id": score_id,
            "traceId": trace_id,
            "name": "chat_quality",
            "value": 1.0,
        },
    )
    observed = {}
    real_writer = runner.ReportWriter

    class SpyWriter(real_writer):
        def __init__(self, *args, **kwargs):
            self.events = []
            super().__init__(*args, **kwargs)
            observed["writer"] = self

        def checkpoint(self, document):
            self.events.append(("checkpoint", document.get("status"), len(document.get("items", []))))
            return super().checkpoint(document)

        def finish(self, status, *, errors=None):
            self.events.append(("finish", status, len(self.document.get("items", []))))
            return super().finish(status, errors=errors)

    monkeypatch.setattr(runner, "ReportWriter", SpyWriter)
    result = runner.run(output_dir=tmp_path, items=[_item()])

    events = observed["writer"].events
    assert result["exit_code"] == 0
    assert events[0] == ("checkpoint", "running", 0)
    assert ("checkpoint", "running", 1) in events
    assert ("finish", "completed", 1) in events
    assert events[-1] == ("checkpoint", "completed", 1)
