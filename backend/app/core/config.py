"""
全局配置。读取 .env 与环境变量，提供单例 settings。

为什么用 pydantic-settings 而不是直接 os.environ：
1. 类型强校验，启动时就能发现缺失/格式错误，不会跑到中途才崩
2. 配合 IDE 类型提示，调用 settings.x 时有自动补全
3. 自动从 .env 加载，无需手写 dotenv 调用
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


# 项目根目录：本文件位于 backend/app/core/config.py，回退三层到仓库根
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _csv_list(raw: str) -> list[str]:
    """解析逗号分隔的字符串成列表。
    .env 不能直接写 list，所以用 string-list 模式"""
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    """运行期全部配置。字段名与 .env 变量一一对应（大小写不敏感）"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # .env 里多余字段忽略，不抛错
    )

    # ===== LLM provider 注册 =====
    # 启用哪些 provider。.env 写 "deepseek,qwen"，下面 validator 转 list
    # 加新 provider：在 services/llm.py 的 _OPENAI_COMPAT_REGISTRY 加一行，
    #              .env 加 KEY/URL，把名字加入 LLM_PROVIDERS
    # Annotated[..., NoDecode] 关闭 pydantic-settings 的 JSON 自动解码，
    # 让 field_validator 接管解析（否则 .env 里写 "deepseek,qwen" 会被当 JSON 报错）
    llm_providers: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["deepseek", "qwen"]
    )

    @field_validator("llm_providers", mode="before")
    @classmethod
    def _parse_llm_providers(cls, v: object) -> object:
        """允许 .env 写 "deepseek,qwen" 而不是 JSON 数组"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # === DeepSeek ===
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # === Qwen 通义 ===
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # === Kimi 月之暗面（可选） ===
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"

    # === GLM 智谱（可选） ===
    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"

    # === StepFun 阶跃（可选） ===
    stepfun_api_key: str = ""
    stepfun_base_url: str = "https://api.stepfun.com/v1"

    # === Doubao 字节豆包（可选） ===
    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"

    # ===== Tier 路由 =====
    # 格式: "provider_name:model_name"
    # 业务代码只关心 PRIMARY/SECONDARY/BACKGROUND 三档，
    # 切换具体模型 = 改这三个字段，0 行业务代码变动
    llm_tier_primary: str = "deepseek:deepseek-chat"
    llm_tier_secondary: str = "qwen:qwen-plus"
    llm_tier_background: str = "qwen:qwen-turbo"

    # ===== 数据库 =====
    postgres_dsn: str = (
        "postgresql://postgres:postgres@localhost:5432/career_multiverse"
    )
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # ===== 阿里云 =====
    aliyun_access_key: str = ""
    aliyun_secret_key: str = ""
    aliyun_oss_bucket: str = ""

    # ===== 运行时 =====
    app_env: str = "dev"
    log_level: str = "INFO"

    # ===== 业务参数（不放 .env，但集中管理） =====
    # 一次完整 simulation = 模拟 3 个月春招
    simulation_months: int = 3

    # 默认并行模拟次数。1000 是产品定位（给用户的"平行宇宙"卖点），
    # demo 时可降到 200 提速。这里默认 1000，运行时可覆盖
    default_simulation_runs: int = 1000

    # 沙盘中虚拟公司数量。50 是兼顾"有代表性"和"模拟成本"的折中
    virtual_companies_count: int = 50

    # 沙盘中其他求职者分身数量。模拟竞争压力，但不能太多否则成本爆炸
    competitor_personas_count: int = 200


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """单例 settings。lru_cache 确保进程内只实例化一次"""
    return Settings()
