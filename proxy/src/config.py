from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BALANCIT_")

    service_a_url: str = "http://service-a.balancit:8000"
    service_b_url: str = "http://service-b.balancit:8000"
    upstream_timeout: float = 10.0
    proxy_port: int = 8080

    # Modes: none, static, ml
    proxy_mode: str = "none"

    # Static token bucket settings
    static_rate_per_second: float = 10.0
    static_bucket_capacity: float = 20.0

    # ML mode Redis settings
    redis_host: str = "redis.balancit"
    redis_port: int = 6379
    redis_timeout: float = 0.5

    # Per-label rate tiers (RPS, capacity)
    rate_genuine_rps: float = 5.0
    rate_genuine_capacity: float = 10.0
    rate_suspicious_rps: float = 1.0
    rate_suspicious_capacity: float = 2.0
    rate_untrusted_rps: float = 2.0
    rate_untrusted_capacity: float = 8.0


settings = Settings()
