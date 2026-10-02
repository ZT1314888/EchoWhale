import logging
from functools import lru_cache
from typing import Annotated, ClassVar

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from api.common.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# AUTH_JWT_SECRET 的开发默认值：生产门控用它识别"没有显式换密钥"的部署。
# 提取为模块常量供测试直接引用，避免测试里硬编码同一字面量。
DEFAULT_JWT_SECRET = "dev-secret-change-me"

# 非生产环境白名单（大小写不敏感）：只有这些值豁免生产清单检查。
# 注意是白名单而非黑名单——APP_ENV 取白名单外的任何值（prod / staging / live /
# 空串 / 拼写错误）一律按生产标准校验（fail-closed）：宁可误报阻止启动，
# 不可漏报带着公开默认密钥上线（可伪造任意用户 token）。
NON_PRODUCTION_ENVS = frozenset({"development", "dev", "test", "testing", "local"})


class Settings(BaseSettings):
    default_frontend_public_base_url: ClassVar[str] = "http://localhost:5173"
    app_name: str = "EchoWhale API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    database_url: str = ""
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout_seconds: int = 30
    database_pool_recycle_seconds: int = 1800
    auth_jwt_secret: str = DEFAULT_JWT_SECRET
    auth_access_token_ttl_seconds: int = 900
    auth_refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14
    auth_refresh_cookie_name: str = "echowhale_refresh_token"
    auth_visitor_cookie_name: str = "echowhale_visitor_id"
    auth_cookie_secure: bool = False
    frontend_public_base_url: str = default_frontend_public_base_url
    redis_url: str = ""
    auth_email_code_ttl_seconds: int = 600
    auth_email_send_cooldown_seconds: int = 60
    auth_email_send_daily_limit: int = 5
    auth_email_verify_max_attempts: int = 5
    auth_smtp_host: str = ""
    auth_smtp_port: int = 465
    auth_smtp_username: str = ""
    auth_smtp_password: str = ""
    auth_smtp_from_email: str = ""
    auth_smtp_from_name: str = "EchoWhale"
    auth_smtp_use_ssl: bool = True
    auth_smtp_use_starttls: bool = False
    auth_mail_queue_name: str = "auth-mail"
    r2_bucket: str = "echo-whale-media"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_endpoint: str = ""
    r2_signed_url_ttl_seconds: int = 900
    media_max_file_size: int = 10 * 1024 * 1024
    media_allowed_content_types: Annotated[list[str], NoDecode] = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]
    # 全局请求体大小门（BodySizeLimitMiddleware）：12MB = 当前业务最大合法 body
    # （10MB 媒体上传）+ multipart 编码余量；未来新增更大 body 的端点时需同步上调。
    max_request_body_bytes: int = 12 * 1024 * 1024
    model_runtime_mode: str = "mock"
    vision_primary_provider: str = "mock"
    vision_primary_base_url: str = ""
    vision_primary_api_key: str = ""
    vision_primary_model: str = ""
    vision_primary_timeout_seconds: int = 30
    vision_fallback_provider: str = "mock"
    vision_fallback_base_url: str = ""
    vision_fallback_api_key: str = ""
    vision_fallback_model: str = ""
    vision_fallback_timeout_seconds: int = 30
    text_primary_provider: str = "mock"
    text_primary_base_url: str = ""
    text_primary_api_key: str = ""
    text_primary_model: str = ""
    text_primary_timeout_seconds: int = 30
    text_fallback_provider: str = "mock"
    text_fallback_base_url: str = ""
    text_fallback_api_key: str = ""
    text_fallback_model: str = ""
    text_fallback_timeout_seconds: int = 30
    llm_request_deadline_seconds: int = 45
    llm_max_retries_per_provider: int = 1
    llm_retry_backoff_seconds: float = 0.5
    # 单次调用输出硬顶（Finding 10a）：max_tokens 是输出上限而非精确计量
    # （不引入 tiktoken），按引擎用途给不同预算，避免单次调用成本上不封顶。
    llm_coach_max_tokens: int = 300
    llm_feedback_max_tokens: int = 400
    llm_scene_max_tokens: int = 500
    # 复盘文案（LLM 复盘，审计 Finding 20）输出预算（Finding 10a 同族）：
    # 复盘是短中文文案，预算给小即可；复盘是增强分支，失败/超时降级模板复盘，
    # 该键只约束单次调用成本，不参与启动校验。
    llm_review_max_tokens: int = 300
    # 复盘分支对回复轮的最大附加等待（秒）：流式路径复盘与教练 delta 并行、
    # 非流式与语音收口路径串行有界等待，超时取消并降级模板复盘，
    # 保证主价值（教练回复）不被增强分支拖慢。
    llm_review_wait_seconds: float = 5.0
    # 教练输出防滥用硬顶（Finding 11）：模型输出超过该字符数直接截断并记
    # coach_reply_truncated warning，超长输出不再无限撑库/撑响应。
    llm_coach_output_max_chars: int = 2000
    llm_coach_window_size: int = 8
    llm_json_mode_enabled: bool = False
    llm_stream_include_usage: bool = False
    llm_session_start_limit: int = 10
    llm_session_start_window_seconds: int = 3600
    llm_reply_limit: int = 30
    llm_reply_window_seconds: int = 3600
    # 匿名访客 IP 维度兜底限额（默认 visitor 限额 ×5）：
    # 键取 TCP 对端地址而非 X-Forwarded-For（XFF 可伪造），共享出口 IP 的
    # 误伤由放大系数吸收。仅作用于 sessions 的 start / reply / reply-stream。
    llm_session_start_ip_limit: int = 50
    llm_reply_ip_limit: int = 150
    # 媒体上传限流：owner 键 + 匿名访客 IP 兜底键（键构造与 sessions 的
    # IP 键同一模式，只取 TCP 对端地址）；窗口复用 3600 秒常量语义。
    media_upload_limit: int = 20
    media_upload_ip_limit: int = 100
    # 语音 bootstrap 限流（Finding 12a）：每次调用都消耗一次 Deepgram token grant，
    # owner 键 + 匿名访客 IP 兜底键；窗口复用 3600 秒常量语义（见 llm_rate_limit）。
    voice_bootstrap_limit: int = 5
    voice_bootstrap_ip_limit: int = 25
    # Deepgram think 代理 per-sid 限流（Finding 12b）：令牌 TTL 内可复用，
    # 配额按会话维度约束（120 次 / 5 分钟对正常语音会话绰绰有余）。
    think_proxy_limit: int = 120
    think_proxy_window_seconds: int = 300
    # 进程内限流字典的键容量上限（LRU 淘汰最久未用键）；
    # Redis 变体不受影响（键自带 TTL，天然有界）。
    rate_limiter_max_keys: int = 10_000
    scene_analysis_cache_enabled: bool = False
    scene_analysis_async_enabled: bool = False
    scene_analysis_prompt_version: str = "v1"
    scene_analysis_queue_name: str = "scene-analysis"
    deepgram_api_key: str = ""
    deepgram_agent_base_url: str = "wss://api.deepgram.com/v1/agent/converse"
    deepgram_agent_token_ttl_seconds: int = 600
    deepgram_agent_language: str = "en"
    deepgram_agent_listen_model: str = "flux-general-en"
    deepgram_agent_listen_version: str = "v2"
    deepgram_agent_listen_eot_threshold: float = 0.7
    deepgram_agent_listen_eager_eot_threshold: float = 0.4
    deepgram_agent_listen_eot_timeout_ms: int = 6000
    deepgram_agent_listen_smart_format: bool = False
    deepgram_agent_speak_model: str = "aura-2-cordelia-en"
    deepgram_agent_output_sample_rate: int = 24000
    deepgram_agent_think_model: str = ""
    deepgram_agent_think_proxy_public_base_url: str = ""
    deepgram_agent_think_upstream_base_url: str = ""
    deepgram_agent_think_upstream_api_key: str = ""
    deepgram_agent_think_timeout_seconds: int = 30
    deepgram_agent_think_token_ttl_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("allowed_origins", "media_allowed_content_types", mode="before")
    @classmethod
    def split_csv_values(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def validate_runtime(self) -> None:
        self._validate_model_runtime()
        self._validate_smtp_settings()

        # 门控反转（fail-closed）：白名单外的任何值一律执行生产清单检查。
        # 空串视为"环境变量未注入"（compose 漏配是最常见的生产事故形态），
        # 按最严格标准校验——宁可误报阻止启动，不可漏报带病上线。
        if self.app_env.strip().lower() not in NON_PRODUCTION_ENVS:
            errors: list[str] = []
            if len(self.auth_jwt_secret) < 32 or self.auth_jwt_secret == DEFAULT_JWT_SECRET:
                errors.append(
                    "AUTH_JWT_SECRET must be a strong value in production "
                    "(not the default and at least 32 characters)"
                )
            if not self.auth_cookie_secure:
                errors.append("AUTH_COOKIE_SECURE must be true in production")
            if not self.allowed_origins:
                errors.append("ALLOWED_ORIGINS must not be empty in production")
            if self.frontend_public_base_url.rstrip("/") == self.default_frontend_public_base_url:
                errors.append("FRONTEND_PUBLIC_BASE_URL must be explicitly set in production")
            if not self.database_url.strip():
                errors.append("DATABASE_URL must be set in production")
            if not self.redis_url.strip():
                errors.append(
                    "REDIS_URL must be set in production (email codes and rate limiting "
                    "would silently degrade to in-process implementations, which breaks "
                    "multi-worker deployments)"
                )
            if self.model_runtime_mode.strip().lower() != "live":
                errors.append(
                    "MODEL_RUNTIME_MODE must be 'live' in production "
                    "(mock mode would silently serve fake model responses)"
                )
            if not self.r2_endpoint.strip():
                errors.append("R2_ENDPOINT must be set in production")
            if not self.r2_access_key_id.strip():
                errors.append("R2_ACCESS_KEY_ID must be set in production")
            if not self.r2_secret_access_key.strip():
                errors.append("R2_SECRET_ACCESS_KEY must be set in production")
            # SMTP 四字段全配才放行：注册→激活链路硬依赖邮件，漏配会让全量
            # 注册无声瘫痪（用户永久卡在 pending_verification）。
            for smtp_field, env_name in (
                ("auth_smtp_host", "AUTH_SMTP_HOST"),
                ("auth_smtp_username", "AUTH_SMTP_USERNAME"),
                ("auth_smtp_password", "AUTH_SMTP_PASSWORD"),
                ("auth_smtp_from_email", "AUTH_SMTP_FROM_EMAIL"),
            ):
                if not getattr(self, smtp_field).strip():
                    errors.append(
                        f"{env_name} must be set in production "
                        "(registration depends on email activation)"
                    )
            if not self.deepgram_api_key.strip():
                errors.append("DEEPGRAM_API_KEY must be set in production")
            if not self.deepgram_agent_base_url.strip():
                errors.append("DEEPGRAM_AGENT_BASE_URL must be set in production")
            if not self.deepgram_agent_think_model.strip():
                errors.append("DEEPGRAM_AGENT_THINK_MODEL must be set in production")

            if errors:
                raise ConfigurationError("; ".join(errors))

        # 生效模式留痕：只打非敏感开关值，帮助部署时确认"生效的是我以为的环境"。
        logger.info(
            "app_env=%s model_runtime_mode=%s scene_analysis_cache=%s",
            self.app_env,
            self.model_runtime_mode,
            self.scene_analysis_cache_enabled,
        )

    def _validate_smtp_settings(self) -> None:
        smtp_enabled = any(
            (
                self.auth_smtp_host.strip(),
                self.auth_smtp_username.strip(),
                self.auth_smtp_password.strip(),
                self.auth_smtp_from_email.strip(),
            )
        )
        if not smtp_enabled:
            return

        errors: list[str] = []
        if not self.auth_smtp_host.strip():
            errors.append("AUTH_SMTP_HOST must be set when SMTP delivery is enabled")
        if not self.auth_smtp_username.strip():
            errors.append("AUTH_SMTP_USERNAME must be set when SMTP delivery is enabled")
        if not self.auth_smtp_password.strip():
            errors.append("AUTH_SMTP_PASSWORD must be set when SMTP delivery is enabled")
        if not self.auth_smtp_from_email.strip():
            errors.append("AUTH_SMTP_FROM_EMAIL must be set when SMTP delivery is enabled")
        if self.auth_smtp_use_ssl and self.auth_smtp_use_starttls:
            errors.append("AUTH_SMTP_USE_SSL and AUTH_SMTP_USE_STARTTLS cannot both be true")

        if errors:
            raise ConfigurationError("; ".join(errors))

    def _validate_model_runtime(self) -> None:
        runtime_mode = self.model_runtime_mode.lower()
        if runtime_mode == "mock":
            return
        if runtime_mode != "live":
            raise ConfigurationError("MODEL_RUNTIME_MODE must be either 'mock' or 'live'")

        errors: list[str] = []
        for prefix in (
            "VISION_PRIMARY",
            "VISION_FALLBACK",
            "TEXT_PRIMARY",
            "TEXT_FALLBACK",
        ):
            provider = getattr(self, f"{prefix.lower()}_provider").strip().lower()
            if provider in {"", "mock"}:
                continue

            if not getattr(self, f"{prefix.lower()}_base_url").strip():
                errors.append(f"{prefix}_BASE_URL must be set when {prefix}_PROVIDER is live")
            if not getattr(self, f"{prefix.lower()}_model").strip():
                errors.append(f"{prefix}_MODEL must be set when {prefix}_PROVIDER is live")

        if errors:
            raise ConfigurationError("; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
