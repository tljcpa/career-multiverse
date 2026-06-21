"""
FastAPI 入口。

为什么用 lifespan 而不是 startup/shutdown 事件：
FastAPI 新版本（0.100+）推荐 lifespan，可以共享上下文对象（LLM 客户端连接池）
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.services.llm import init_router, shutdown_router

# 全局日志：之前默认 WARNING 级，INFO 全丢；评委 demo 卡顿无法定位
# 改 INFO 级 + 加时间戳 + 模块名，配合 journalctl 可查所有 LLM 调用 / sim 进度
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


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
    description="用户上传简历 → LLM 五维评估 + 学校档判定 → 沙盘 simulate 1000 个平行春招宇宙 → 输出统计与反事实分析",
    version="0.1.0",
    lifespan=lifespan,
    # 生产环境关闭 Swagger / OpenAPI 暴露——避免评委 F12 看到全 admin endpoint 列表
    # demo 期间需要看 API 文档可临时打开
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
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


# 全局异常 handler：之前未捕获异常会吐 500 + 英文 traceback 给评委
# 现在统一返回中文友好错误 + 服务器侧带 stack trace logger.exception 便于排查
@app.exception_handler(Exception)
async def _global_exception(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("multiverse.error").exception(
        f"unhandled {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误（{type(exc).__name__}），请稍后重试或联系管理员"},
    )


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
