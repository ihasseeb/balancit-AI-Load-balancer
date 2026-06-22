from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BALANCIT_")

    prometheus_url: str = "http://prometheus-kube-prometheus-prometheus.monitoring:9090"
    scrape_interval: int = 5
    namespace: str = "balancit"

    # HST settings
    hst_n_trees: int = 10
    hst_height: int = 8
    hst_window_size: int = 100
    hst_warmup_samples: int = 60

    suspicious_percentile: float = 0.90
    anomaly_percentile: float = 0.99

    # Forecaster settings
    forecast_horizon: int = 6
    forecaster_warmup_samples: int = 20

    # Publisher settings
    redis_host: str = "redis.balancit"
    redis_port: int = 6379
    redis_ttl_seconds: int = 60
    metrics_port: int = 8000


settings = Settings()
