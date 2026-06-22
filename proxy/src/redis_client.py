import redis
from .config import settings


class LabelReader:
    """Read-only Redis client for fetching ML labels."""

    def __init__(self):
        self.client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
            socket_timeout=settings.redis_timeout,
            socket_connect_timeout=settings.redis_timeout,
        )

    def get_label(self, client_id: str) -> str | None:
        """Return the label or None if Redis is unreachable or no label exists."""
        try:
            return self.client.get(f"client:{client_id}:label")
        except Exception:
            return None
