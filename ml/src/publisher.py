import redis
from prometheus_client import Gauge, start_http_server
from .config import settings


ml_client_signal = Gauge(
    "ml_client_signal",
    "Forecasted genuine load per client (RPS)",
    ["client_id", "service"],
)
ml_client_score = Gauge(
    "ml_client_score",
    "HST anomaly score per client (0 to 1)",
    ["client_id", "service"],
)
ml_client_rps = Gauge(
    "ml_client_rps",
    "Current observed RPS per client",
    ["client_id", "service"],
)


class Publisher:
    def __init__(self):
        self.redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
            socket_timeout=2.0,
        )
        start_http_server(settings.metrics_port)
        print(f"[publisher] Prometheus metrics exposed on :{settings.metrics_port}", flush=True)

    def publish(self, client_id: str, service: str, rps: float, score: float, label: str, forecast: float | None):
        # Idle clients should not contribute to scaling signal
        if label == "IDLE":
            scaling_signal = 0.0
        else:
            scaling_signal = forecast if forecast is not None else rps

        ml_client_signal.labels(client_id=client_id, service=service).set(scaling_signal)
        ml_client_score.labels(client_id=client_id, service=service).set(score)
        ml_client_rps.labels(client_id=client_id, service=service).set(rps)

        try:
            key_prefix = f"client:{client_id}"
            pipe = self.redis.pipeline()
            pipe.setex(f"{key_prefix}:label", settings.redis_ttl_seconds, label)
            pipe.setex(f"{key_prefix}:score", settings.redis_ttl_seconds, f"{score:.4f}")
            pipe.setex(
                f"{key_prefix}:forecast",
                settings.redis_ttl_seconds,
                f"{forecast:.4f}" if forecast is not None else "null",
            )
            pipe.setex(f"{key_prefix}:scaling_signal", settings.redis_ttl_seconds, f"{scaling_signal:.4f}")
            pipe.execute()
        except Exception as e:
            print(f"[publisher] redis write failed for {client_id}: {e}", flush=True)
