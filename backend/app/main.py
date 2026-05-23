"""
FastAPI 入口。

为什么用 lifespan 而不是 startup/shutdown 事件：
FastAPI 新版本（0.100+）推荐 lifespan，可以共享上下文对象（LLM 客户端连接池）
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.services.llm import init_router, shutdown_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期。yield 之前是启动，之后是关闭"""
    settings = get_settings()
    router = init_router()
    # 启动时打印当前 LLM 路由，便于确认配置生效
    routing = router.describe_routing()
    print(f"[startup] env={settings.app_env}")
    for tier_name, target in routing.items():
        print(f"[startup] LLM tier {tier_name} -> {target}")
    try:
        yield
    finally:
        await shutdown_router()
        print("[shutdown] LLM router 已关闭")


app = FastAPI(
    title="春招平行宇宙 / Career Multiverse",
    description="用户上传简历 → LoRA 微调数字分身 → 沙盘 simulate 1000 次完整春招 → 输出统计与反事实分析",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS：dev 阶段 frontend 跑在 :5173/5174，backend 在 :8000，跨域必开
# 生产环境（同域部署）可以收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 API 路由（/api/*）
app.include_router(api_router)
# 挂载 admin 路由（/api/admin/*）— 公司池 + 求职者池 CRUD
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """根路径健康检查。Docker / 阿里云 SLB 用"""
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "career-multiverse",
        "version": "0.1.0",
        "docs": "/docs",
    }
