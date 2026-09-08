import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

from backend.app.article_assistant.domain.article import ArticleCandidate, ArticleTask
from backend.app.platform.config import BASE_DIR


class TaskStore:
    def __init__(self, database_path: Optional[Path] = None):
        # 允许通过环境变量 AGENT_TASKS_DB 覆盖默认路径（例如受限环境下指向 /tmp）。
        env_path = os.environ.get("AGENT_TASKS_DB")
        self.database_path = database_path or (Path(env_path) if env_path else BASE_DIR / "data" / "agent_tasks.sqlite3")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS article_tasks (task_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    def save(self, task: ArticleTask) -> None:
        payload = json.dumps(self._to_dict(task), ensure_ascii=False)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO article_tasks(task_id, payload) VALUES(?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload",
                (task.task_id, payload),
            )

    def get(self, task_id: str) -> Optional[ArticleTask]:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT payload FROM article_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._from_dict(json.loads(row[0])) if row else None

    @staticmethod
    def _to_dict(task: ArticleTask) -> dict:
        payload = dict(task.__dict__)
        payload["candidates"] = [candidate.__dict__ for candidate in task.candidates]
        return payload

    @staticmethod
    def _from_dict(payload: dict) -> ArticleTask:
        payload["candidates"] = [ArticleCandidate(**candidate) for candidate in payload.get("candidates", [])]
        return ArticleTask(**payload)
