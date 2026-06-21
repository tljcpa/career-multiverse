"""
管理员接口：公司池 / 求职者池的 CRUD + 持久化。

产品定位：沙盘是动态市场，公司和求职者可随时加入退出。
- 加入：POST 提交完整 schema
- 退出：DELETE by id
- 修改：PATCH 局部字段
- 列举：GET 全量

数据层选择：JSON 文件 + threading.Lock（写时全文重写）。
为什么不上 SQLite：50 公司 + 200 persona 规模 JSON 全文 < 1MB，
每次 sim 启动 snapshot 一次也只 <50ms，工程复杂度 < SQLite ORM。
未来规模上千时再迁移。

并发安全：
- 写：threading.Lock 锁住读 + 修改 + 落盘
- 读：sim 启动时 snapshot list（浅拷贝），sim 内部不会被并发修改影响
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from ..models.candidate import CandidateProfile
from ..models.company import CompanyProfile

# ===== 配置 =====

PROJECT_ROOT = Path(__file__).resolve().parents[3]
COMPANIES_FILE = PROJECT_ROOT / "backend" / "data" / "companies" / "companies_v1.json"
PERSONAS_FILE = PROJECT_ROOT / "backend" / "data" / "personas" / "competitors_v1.json"

# admin token：env 没设就用默认（demo 用），生产化前必须改
_ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "multiverse-demo-2026")

# 文件锁（per-file）
_companies_lock = threading.Lock()
_personas_lock = threading.Lock()

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _check_token(x_admin_token: str | None = Header(default=None)) -> None:
    """简单 token 鉴权。所有 admin endpoint 必须带 X-Admin-Token header"""
    if x_admin_token != _ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Admin-Token 缺失或不正确",
        )


# ===== 通用底层读写 =====


def _atomic_write_json(path: Path, payload: list[dict]) -> None:
    """原子写：先写到临时文件，再 rename。
    避免写一半进程崩溃时主文件损坏"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件放同一目录，确保 rename 是同分区原子操作
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        suffix=".tmp",
        delete=False,
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    # rename 是 POSIX 原子操作
    shutil.move(tmp_path, str(path))


def _load_json_list(path: Path) -> list[dict]:
    """读 JSON 文件。文件不存在或为空返回空列表"""
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


# ===== 公司 CRUD =====


@router.get("/companies", dependencies=[Depends(_check_token)])
def list_companies() -> list[dict]:
    """列出公司池全量。前端管理页用"""
    return _load_json_list(COMPANIES_FILE)


@router.get("/companies/{code_name}", dependencies=[Depends(_check_token)])
def get_company(code_name: str) -> dict:
    items = _load_json_list(COMPANIES_FILE)
    for c in items:
        if c.get("code_name") == code_name:
            return c
    raise HTTPException(status_code=404, detail=f"公司 {code_name} 不存在")


@router.post(
    "/companies",
    status_code=201,
    dependencies=[Depends(_check_token)],
)
def add_company(profile: CompanyProfile) -> dict:
    """添加新公司。code_name 必须唯一"""
    with _companies_lock:
        items = _load_json_list(COMPANIES_FILE)
        if any(c.get("code_name") == profile.code_name for c in items):
            raise HTTPException(
                status_code=409,
                detail=f"公司代号 {profile.code_name} 已存在",
            )
        new_item = profile.model_dump(mode="json")
        items.append(new_item)
        _atomic_write_json(COMPANIES_FILE, items)
    return {"status": "added", "company": new_item, "total": len(items)}


@router.patch("/companies/{code_name}", dependencies=[Depends(_check_token)])
def update_company(code_name: str, patch: dict[str, Any]) -> dict:
    """局部更新。请求体直接是要更新的字段（如 {"hidden_signals": {"hiring_bar": 75}}）"""
    with _companies_lock:
        items = _load_json_list(COMPANIES_FILE)
        idx = next(
            (i for i, c in enumerate(items) if c.get("code_name") == code_name),
            None,
        )
        if idx is None:
            raise HTTPException(status_code=404, detail=f"公司 {code_name} 不存在")
        merged = _deep_merge(items[idx], patch)
        # Pydantic 验证保证修改后仍合法
        try:
            CompanyProfile.model_validate(merged)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"修改后字段不合法: {e}")
        items[idx] = merged
        _atomic_write_json(COMPANIES_FILE, items)
    return {"status": "updated", "company": merged}


@router.delete("/companies/{code_name}", dependencies=[Depends(_check_token)])
def delete_company(code_name: str) -> dict:
    """退出沙盘：硬删（也可以做软删，看用户偏好）"""
    with _companies_lock:
        items = _load_json_list(COMPANIES_FILE)
        before = len(items)
        items = [c for c in items if c.get("code_name") != code_name]
        if len(items) == before:
            raise HTTPException(status_code=404, detail=f"公司 {code_name} 不存在")
        _atomic_write_json(COMPANIES_FILE, items)
    return {"status": "deleted", "code_name": code_name, "remaining": len(items)}


# ===== 求职者 CRUD =====


@router.get("/personas", dependencies=[Depends(_check_token)])
def list_personas() -> list[dict]:
    return _load_json_list(PERSONAS_FILE)


@router.get("/personas/{candidate_id}", dependencies=[Depends(_check_token)])
def get_persona(candidate_id: str) -> dict:
    items = _load_json_list(PERSONAS_FILE)
    for p in items:
        if p.get("candidate_id") == candidate_id:
            return p
    raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")


@router.post(
    "/personas",
    status_code=201,
    dependencies=[Depends(_check_token)],
)
def add_persona(profile: CandidateProfile) -> dict:
    """加入沙盘"""
    with _personas_lock:
        items = _load_json_list(PERSONAS_FILE)
        if any(p.get("candidate_id") == profile.candidate_id for p in items):
            raise HTTPException(
                status_code=409,
                detail=f"候选人 ID {profile.candidate_id} 已存在",
            )
        new_item = profile.model_dump(mode="json")
        items.append(new_item)
        _atomic_write_json(PERSONAS_FILE, items)
    return {"status": "added", "persona": new_item, "total": len(items)}


@router.patch("/personas/{candidate_id}", dependencies=[Depends(_check_token)])
def update_persona(candidate_id: str, patch: dict[str, Any]) -> dict:
    with _personas_lock:
        items = _load_json_list(PERSONAS_FILE)
        idx = next(
            (i for i, p in enumerate(items) if p.get("candidate_id") == candidate_id),
            None,
        )
        if idx is None:
            raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")
        merged = _deep_merge(items[idx], patch)
        try:
            CandidateProfile.model_validate(merged)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"修改后字段不合法: {e}")
        items[idx] = merged
        _atomic_write_json(PERSONAS_FILE, items)
    return {"status": "updated", "persona": merged}


@router.delete("/personas/{candidate_id}", dependencies=[Depends(_check_token)])
def delete_persona(candidate_id: str) -> dict:
    with _personas_lock:
        items = _load_json_list(PERSONAS_FILE)
        before = len(items)
        items = [p for p in items if p.get("candidate_id") != candidate_id]
        if len(items) == before:
            raise HTTPException(status_code=404, detail=f"候选人 {candidate_id} 不存在")
        _atomic_write_json(PERSONAS_FILE, items)
    return {"status": "deleted", "candidate_id": candidate_id, "remaining": len(items)}


# ===== 工具 =====


def _deep_merge(base: dict, patch: dict) -> dict:
    """递归合并 patch 到 base。patch 里 None 会覆盖（保留删除字段语义）"""
    result = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
