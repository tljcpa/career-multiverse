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
    # LLM 真评估的 5 维评分理由（B 方案：透明化"AI 怎么打这个分"）
    # key: project_strength / internship_strength / achievements_strength
    #      / communication_score / gpa_percentile / school_tier
    # value: 一句自然语言理由
    evaluation_reasoning: dict[str, str] = field(default_factory=dict)


@dataclass
class SimSession:
    """一次 sim 任务的状态"""

    sim_session_id: str
    user_id: str
    total_runs: int
    created_at: float
    # 真跑的少量 sim 结果
    real_outcomes: list[Any] = field(default_factory=list)
    # 每次 sim 的事件流（按 sim_idx 顺序），用于 Sandbox 3D 展示真实投递动画
    # 之前 Sandbox 用 sim_smoke.json 静态文件，故事-实现裂缝；改用真 events
    events_by_sim: list[list[dict]] = field(default_factory=list)
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
        # HR 多轮对话历史：key=(user_id, company_code) → list of {"role","content"}
        # 之前评委要求"回顾/总结刚才所有回答"时会穿帮（LLM 不知道前文）。现在保留 20 轮 = 40 条
        self._chats: dict[tuple[str, str], list[dict]] = {}

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

    def _chat_file(self, user_id: str, company_code: str) -> Path:
        """计算某 (user, company) 对话历史的落盘路径，并做文件名安全处理。

        路径形如 data/users/{user_id}/chat_{company_code}.json。
        company_code 可能来自外部输入（甚至含 ../），所以复用 save_uploaded_resume
        的防御：先 Path(...).name 去掉任何目录分量，再 resolve 后校验仍在用户目录内。
        """
        # user_id 同样去掉目录分量，防止 user_id='../other' 跨用户写
        safe_uid = Path(user_id or "anon").name or "anon"
        user_dir = USER_DATA_DIR / safe_uid
        # company_code 去掉路径分量；为空时给个兜底名，避免生成 chat_.json 之外的怪文件
        safe_company = Path(company_code).name
        if not safe_company:
            safe_company = "unknown"
        # 防超长：多数文件系统单个文件名上限 255 字节，中文 UTF-8 每字 3 字节，
        # 加 "chat_" + ".json" 前后缀约 10 字节，故按字节截断到 200 留足余量。
        # 截断后用稳定 hash 后缀保证不同长名不会碰撞到同一文件。
        encoded = safe_company.encode("utf-8")
        if len(encoded) > 200:
            import hashlib

            digest = hashlib.sha1(encoded).hexdigest()[:8]
            # 按字节安全截断到 180，再 decode 忽略截断处的半个多字节字符
            truncated = encoded[:180].decode("utf-8", errors="ignore")
            safe_company = f"{truncated}_{digest}"
        # 拼出最终文件名，整体 resolve 后再校验，双保险防 path traversal
        out = (user_dir / f"chat_{safe_company}.json").resolve()
        if not str(out).startswith(str(USER_DATA_DIR.resolve())):
            raise ValueError(f"非法 company_code（path traversal 尝试）: {company_code}")
        return out

    def _read_chat_file(self, path: Path) -> list[dict]:
        """从磁盘读对话历史；文件不存在或损坏都回退空 list（容错优先）"""
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 文件被截断 / 并发写到一半 / 编码异常时不抛，返回空让对话继续
            return []
        if isinstance(data, list):
            return data
        else:
            return []

    def get_chat(self, user_id: str, company_code: str) -> list[dict]:
        """拿 HR 多轮对话历史。文件是 source of truth，内存只做加速缓存。

        进程重启 / 60s 后内存可能丢失（后台 sim 并发、GC、进程波动），
        所以这里总是以文件内容为准，读到后顺便回填内存缓存。
        """
        key = (user_id or "anon", company_code)
        path = self._chat_file(user_id, company_code)
        with self._lock:
            # 文件优先：从磁盘恢复，保证跨进程 / 跨时间一致
            lst = self._read_chat_file(path)
            # write-through cache 回填，下次同进程内可直接命中（但仍以文件为准）
            self._chats[key] = list(lst)
            # 返回拷贝，避免调用方在锁外修改内部缓存
            return list(lst)

    def append_chat(self, user_id: str, company_code: str, role: str, content: str) -> None:
        """追加一条对话并落盘。超过 40 条（20 轮）从头丢 2 条保 user+assistant 配对。

        读现有 json → append → 写回。整个过程在 self._lock 下完成，
        和本类其他写操作风格一致（单机进程内串行化，避免并发读改写丢数据）。
        """
        key = (user_id or "anon", company_code)
        path = self._chat_file(user_id, company_code)
        with self._lock:
            # 以文件为准读出当前历史（而不是信任可能已被 GC 的内存缓存）
            lst = self._read_chat_file(path)
            lst.append({"role": role, "content": content})
            if len(lst) > 40:
                # 丢最早 2 条（保偶数），防止 LLM 看到孤儿 assistant
                del lst[:2]
            # 确保目录存在后整体写回（原 json 内容被新 list 覆盖）
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(lst, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # 同步 write-through cache
            self._chats[key] = list(lst)


# 全局单例
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store


# 上传的简历文件落盘位置
USER_DATA_DIR = Path(__file__).resolve().parents[3] / "backend" / "data" / "users"


def save_uploaded_resume(user_id: str, filename: str, content: bytes) -> Path:
    """把上传的简历落盘。
    安全：只取 basename + 防 path traversal（如 filename='../../../etc/cron.d/x'）"""
    user_dir = USER_DATA_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    # 只取文件名（去掉路径），再次防御性 resolve 校验在 USER_DATA_DIR 内
    safe_name = Path(filename).name or "resume.bin"
    out = (user_dir / safe_name).resolve()
    if not str(out).startswith(str(USER_DATA_DIR.resolve())):
        raise ValueError(f"非法文件名（path traversal 尝试）: {filename}")
    out.write_bytes(content)
    return out


def save_user_meta(user_id: str, meta: dict) -> None:
    """保存用户元信息（GitHub URL / blog 等）"""
    user_dir = USER_DATA_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
