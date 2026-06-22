import httpx
from typing import Optional


class PrometheusClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def query(self, promql: str) -> Optional[list]:
        try:
            response = httpx.get(
                f"{self.base_url}/api/v1/query",
                params={"query": promql},
                timeout=5.0
            )
            data = response.json()
            if data["status"] == "success":
                return data["data"]["result"]
            return None
        except Exception as e:
            print(f"[prometheus_client] query failed: {e}", flush=True)
            return None
