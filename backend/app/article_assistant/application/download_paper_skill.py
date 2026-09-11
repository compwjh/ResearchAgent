import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Iterator, Optional
from urllib.parse import urlparse

from backend.app.article_assistant.domain.article import ArticleCandidate
from backend.app.article_assistant.infrastructure.article_download import download_article, safe_filename
from backend.app.platform.config import BASE_DIR
from backend.app.platform.ollama import create_chat_model

SKILL_NAME = "download-paper"
WORKER_MODEL = "deepseek-coder:33b"
# spec-023 Task05：原为机器相关绝对路径 `/Users/wjh/.codex/skills/download-paper`，
# 在本机并不存在且无法跨机器复用。改为项目内相对路径，与 Skill 注册表
# （`.agents/skills/`）保持同一事实源。
SKILL_DIR = BASE_DIR / ".agents" / "skills" / "download-paper"
SKILL_FILES = (SKILL_DIR / "SKILL.md", SKILL_DIR / "scripts" / "download_pdf.py")

PUBLIC_HTTPS = "public_https"
COOKIE_SESSION = "cookie_session"
POW_CHALLENGE = "pow_challenge"
LITERATURE_MUTUAL_AID = "literature_mutual_aid"


class OpenCliUnavailable(Exception):
    """skill 需要 opencli 浏览器工具来获取凭据，但当前不可用。"""

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _read_skill_metadata() -> dict:
    """读取受信任 skill 的元信息（仅 frontmatter 的 name / version 等字段）。

    不读取脚本正文，不执行任何脚本，避免泄露本地路径以外的敏感配置。
    """
    skill_md = SKILL_FILES[0]
    if not skill_md.is_file():
        return {}
    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    meta: dict = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta


def skill_status(available_models: Iterable[str]) -> dict:
    missing_files = [str(path.relative_to(SKILL_DIR)) for path in SKILL_FILES if not path.is_file()]
    worker_available = WORKER_MODEL in set(available_models)
    metadata = _read_skill_metadata()
    return {
        "skill_name": SKILL_NAME,
        "available": not missing_files and worker_available,
        "skill_path": str(SKILL_DIR),
        "version": metadata.get("version"),
        "declared_name": metadata.get("name"),
        "missing_files": missing_files,
        "worker_model": WORKER_MODEL,
        "worker_model_available": worker_available,
    }


def _is_public_https_pdf(candidate: ArticleCandidate) -> bool:
    return candidate.pdf_url_status == "public_pdf" and bool(candidate.pdf_url) and urlparse(candidate.pdf_url).scheme == "https"


def _json_object(content: object) -> dict:
    text = content if isinstance(content, str) else str(content)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def build_download_plan(candidate: ArticleCandidate, worker_model: str = WORKER_MODEL) -> dict:
    if worker_model != WORKER_MODEL:
        raise ValueError("只允许使用受控子模型 deepseek-coder:33b")
    if not _is_public_https_pdf(candidate):
        raise ValueError("候选文章尚未确认存在公开 HTTPS PDF")

    prompt = (
        "为下面已经授权的公开 PDF 下载任务生成 JSON，仅包含 user_message 字段。"
        "不要输出 URL、路径、命令、Cookie、凭据或任何下载步骤。"
        f"标题：{candidate.title}\n来源：{candidate.source_name}"
    )
    response = create_chat_model(worker_model).invoke(prompt)
    suggested = _json_object(getattr(response, "content", response))
    message = suggested.get("user_message")
    if not isinstance(message, str) or not message.strip() or len(message) > 300:
        message = "已确认公开 PDF，可以由下载服务保存并完成校验。"

    return {
        "skill_name": SKILL_NAME,
        "execution_mode": "public_download",
        "candidate_id": candidate.candidate_id,
        "pdf_url": candidate.pdf_url,
        "output_filename": safe_filename(candidate.title),
        "user_message": message.strip(),
    }


def decide_download_method(candidate: ArticleCandidate) -> str:
    """由 skill 决定下载方式：公开 HTTPS PDF 直接走后端；其余归入需凭据的受限方式。"""
    if _is_public_https_pdf(candidate):
        return PUBLIC_HTTPS
    url = (candidate.pdf_url or candidate.article_url or "").lower()
    source = (candidate.source_name or "").lower()
    if "ablesci" in url or "科研通" in source or "互助" in source:
        return LITERATURE_MUTUAL_AID
    if "pmc" in url or "ncbi" in url:
        return POW_CHALLENGE
    return COOKIE_SESSION


def _sanitize_cookie(cookie_str: str) -> str:
    """仅保留 ASCII 的 name=value 对，规避浏览器 eval 输出中的非 latin-1 字符。"""
    pairs = []
    for part in re.sub(r"[^\x20-\x7E]", "", cookie_str).split(";"):
        part = part.strip()
        if "=" in part:
            pairs.append(part)
    return "; ".join(pairs)


def fetch_cookies_via_opencli(browser_session: Optional[str] = None) -> str:
    """通过本机 opencli 浏览器工具获取 Cookie（凭据仅由工具提供，不由模型生成）。"""
    opencli = shutil.which("opencli")
    if not opencli:
        raise OpenCliUnavailable("本机未安装 opencli，无法获取浏览器 Cookie / 解 PoW")
    command = [opencli, "browser"]
    if browser_session:
        command.append(browser_session)
    command += ["eval", "document.cookie"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    except Exception as error:
        raise OpenCliUnavailable(f"调用 opencli 失败：{error}") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise OpenCliUnavailable(f"opencli 返回错误：{detail}")
    return _sanitize_cookie(completed.stdout)


def download_under_skill(candidate: ArticleCandidate, settings, browser_session: Optional[str] = None) -> Iterator[dict]:
    """skill 主导的下载执行：skill 决定方式，真正下载由受限后端服务完成。"""
    method = decide_download_method(candidate)
    if method == PUBLIC_HTTPS:
        for event in download_article(candidate, settings):
            event = dict(event)
            event.setdefault("skill_name", SKILL_NAME)
            event.setdefault("download_method", method)
            yield event
        return
    try:
        cookies = fetch_cookies_via_opencli(browser_session)
    except OpenCliUnavailable as error:
        yield {
            "type": "error",
            "skill_name": SKILL_NAME,
            "download_method": method,
            "download_outcome": "source_unavailable",
            "user_message": (
                f"该文章需要登录或受限访问，skill 需通过 opencli 获取浏览器凭据，但当前不可用：{error}。"
                "请安装并配置 opencli 与可控浏览器，或在浏览器完成登录后重试。"
            ),
        }
        return
    referer = candidate.article_url or candidate.pdf_url
    headers = {"Cookie": cookies}
    if referer:
        headers["Referer"] = referer
    for event in download_article(candidate, settings, extra_headers=headers):
        event = dict(event)
        event.setdefault("skill_name", SKILL_NAME)
        event.setdefault("download_method", method)
        yield event


def build_skill_plan(candidate: ArticleCandidate, worker_model: str = WORKER_MODEL) -> dict:
    """由 skill 主导生成"下载计划"：skill 决定下载方式，真正的下载仍由受限后端执行。

    与 003 的 build_download_plan 不同，本函数不拒绝受限 / 付费候选——skill 会判定方式，
    需要凭据时标记 requires_credentials，由用户已授权的本机浏览器工具（opencli）提供凭据。
    """
    method = decide_download_method(candidate)
    plan = {
        "skill_name": SKILL_NAME,
        "orchestration": "skill_led",
        "download_method": method,
        "requires_credentials": method != PUBLIC_HTTPS,
        "candidate_id": candidate.candidate_id,
        "pdf_url": candidate.pdf_url,
        "output_filename": safe_filename(candidate.title),
    }
    if method == PUBLIC_HTTPS:
        try:
            plan["execution_mode"] = "public_download"
            plan["user_message"] = build_download_plan(candidate, worker_model)["user_message"]
        except ValueError:
            plan["execution_mode"] = "public_download"
            plan["user_message"] = "已确认公开 PDF，可以由下载服务保存并完成校验。"
    else:
        plan["execution_mode"] = "skill_led_restricted"
        plan["user_message"] = (
            "该文章需登录或受限访问，skill 将主导通过凭据来源（opencli 浏览器工具）"
            "获取凭据后由后端完成下载；当前需先安装并配置 opencli 与可控浏览器。"
        )
    return plan
