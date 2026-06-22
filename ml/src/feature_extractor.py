import math
from .prometheus_client import PrometheusClient
from .config import settings


class FeatureExtractor:
    def __init__(self):
        self.client = PrometheusClient(settings.prometheus_url)

    def _get_rps(self, client_id: str) -> tuple[float, dict[str, float]]:
        """Returns total RPS (successful requests only) and per-service breakdown."""
        result = self.client.query(
            f'sum by (service) (rate(proxy_requests_total{{client_id="{client_id}", status!~"4..|5.."}}[1m]))'
        )

        if not result:
            return 0.0, {}

        per_service = {r["metric"].get("service", "unknown"): float(r["value"][1]) for r in result}
        return sum(per_service.values()), per_service

    def _get_error_rate(self, client_id: str) -> float:
        total = self.client.query(
            f'sum(rate(proxy_requests_total{{client_id="{client_id}"}}[1m]))'
        )
        errors = self.client.query(
            f'sum(rate(proxy_requests_total{{client_id="{client_id}", status=~"5.."}}[1m]))'
        )
        total_sum = float(total[0]["value"][1]) if total else 0.0
        error_sum = float(errors[0]["value"][1]) if errors else 0.0
        if total_sum == 0:
            return 0.0
        return error_sum / total_sum

    def _get_service_entropy(self, per_service: dict[str, float]) -> float:
        """Shannon entropy across services hit by this client. Low = single target."""
        total = sum(per_service.values())
        if total == 0:
            return 0.0
        probs = [v / total for v in per_service.values() if v > 0]
        if len(probs) <= 1:
            return 0.0
        return -sum(p * math.log2(p) for p in probs)

    def _get_active_clients(self) -> list[str]:
        result = self.client.query(
            'rate(proxy_requests_total{status!~"4..|5.."}[1m])'
        )
        if not result:
            return []
        clients = list({
            r["metric"].get("client_id", "")
            for r in result
            if r["metric"].get("client_id") and r["metric"].get("client_id") != "unknown"
        })
        return clients

    def extract(self) -> list[dict]:
        clients = self._get_active_clients()
        if not clients:
            return []

        features = []
        for client_id in clients:
            rps, per_service = self._get_rps(client_id)
            dominant_service = max(
                per_service, key=per_service.get) if per_service else "unknown"
            features.append({
                "client_id": client_id,
                "rps": round(rps, 4),
                "service": dominant_service,
                "error_rate": round(self._get_error_rate(client_id), 4),
                "service_entropy": round(self._get_service_entropy(per_service), 4),
            })
        return features
