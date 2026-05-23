"""
In-memory session store。

不引入 Redis 因为 demo 单机部署足够。生产化时换 Redis 就行。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from ..models.candidate import CandidateProfile


@dataclass
class UserSession:
    """一个用户的全部状态（上传 + sim + 反事实）"""

    user_id: str
    created_at: float
    primary_candidate: CandidateProfile | None = None
    raw_resume_text: str = ""
    github_url: str = ""
    blog_url: str = ""


@dataclass
class SimSession:
    """一次 sim 任务的状态"""

    sim_session_id: str
    user_id: str
    total_runs: int
    created_at: float
    # 真跑的少量 sim 结果
    real_outcomes: list[Any] = field(default_factory=list)
    # 真 sim 跑完时间（用于 status 推断）
    started_real_sim_at: float = 0.0
    completed_real_sim_at: float = 0.0
    # 完整聚合结果（从 real_outcomes + 统计推断生成）
    aggregate_cache: Any = None


class SessionStore:
    """线程安全 in-memory session"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._users: dict[str, UserSession] = {}
        self._sims: dict[str, SimSession] = {}

    def create_user(self) -> UserSession:
        uid = f"user_{uuid.uuid4().hex[:8]}"
        sess = UserSession(user_id=uid, created_at=time.time())
        with self._lock:
            self._users[uid] = sess
        return sess

    def get_user(self, user_id: str) -> UserSession | None:
        with self._lock:
            return self._users.get(user_id)

    def create_sim(self, user_id: str, total_runs: int) -> SimSession:
        sid = f"sim_{uuid.uuid4().hex[:10]}"
        sess = SimSession(
            sim_session_id=sid,
            user_id=user_id,
            total_runs=total_runs,
            created_at=time.time(),
        )
        with self._lock:
            self._sims[sid] = sess
        return sess

    def get_sim(self, sim_id: str) -> SimSession | None:
        with self._lock:
            return self._sims.get(sim_id)


# 全局单例
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store


# 上传的简历文件落盘位置
USER_DATA_DIR = Path(__file__).resolve().parents[3] / "backend" / "data" / "users"


def save_uploaded_resume(user_id: str, filename: str, content: bytes) -> Path:
    """把上传的简历落盘"""
    user_dir = USER_DATA_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    out = user_dir / filename
    out.write_bytes(content)
    return out


def save_user_meta(user_id: str, meta: dict) -> None:
    """保存用户元信息（GitHub URL / blog 等）"""
    user_dir = USER_DATA_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
