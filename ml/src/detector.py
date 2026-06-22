from collections import deque, defaultdict
from river import anomaly
from .config import settings


FEATURE_LIMITS = {
    "rps": (0.0, 100.0),
    "error_rate": (0.0, 1.0),
    "service_entropy": (0.0, 2.0),
}


class HSTDetector:
    """One HST model per client. Each client warms up and is classified independently."""

    def __init__(self):
        self.models: dict = {}
        self.score_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.samples_seen: dict[str, int] = defaultdict(int)
        self.thresholds: dict[str, tuple[float, float]] = {}

    def _new_model(self):
        return anomaly.HalfSpaceTrees(
            n_trees=settings.hst_n_trees,
            height=settings.hst_height,
            window_size=settings.hst_window_size,
            limits=FEATURE_LIMITS,
            seed=42,
        )

    def _get_model(self, client_id: str):
        if client_id not in self.models:
            self.models[client_id] = self._new_model()
        return self.models[client_id]

    def _is_idle(self, x: dict) -> bool:
        return all(v == 0 for v in x.values())

    def _sanitize(self, x: dict) -> dict:
        return {k: max(0.0, v) for k, v in x.items()}

    def _is_warmed_up(self, client_id: str) -> bool:
        return self.samples_seen[client_id] >= settings.hst_warmup_samples

    def _calibrate(self, client_id: str):
        history = self.score_history[client_id]
        if len(history) < 30:
            return
        sorted_scores = sorted(history)
        score_range = sorted_scores[-1] - sorted_scores[0]

        # Stable traffic: percentiles are unreliable, use safe conservative thresholds
        if score_range < 0.05:
            self.thresholds[client_id] = (0.5, 0.7)
            return

        n = len(sorted_scores)
        susp_idx = int(n * settings.suspicious_percentile)
        anom_idx = int(n * settings.anomaly_percentile)
        # Floors raised so normal variation isn't flagged
        susp = max(sorted_scores[min(susp_idx, n - 1)], 0.5)
        anom = max(sorted_scores[min(anom_idx, n - 1)], 0.7)
        self.thresholds[client_id] = (susp, anom)

    def _classify(self, client_id: str, score: float) -> str:
        if not self._is_warmed_up(client_id):
            return "WARMUP"
        thresholds = self.thresholds.get(client_id)
        if thresholds is None:
            if score >= 0.5:
                return "ANOMALY"
            if score >= 0.3:
                return "SUSPICIOUS"
            return "GENUINE"
        susp, anom = thresholds
        if score >= anom:
            return "ANOMALY"
        if score >= susp:
            return "SUSPICIOUS"
        return "GENUINE"

    def process(self, features: dict) -> dict:
        client_id = features["client_id"]
        x = {k: v for k, v in features.items() if k not in ("client_id", "service")}
        x = self._sanitize(x)

        if self._is_idle(x):
            return {"client_id": client_id, "score": 0.0, "label": "IDLE"}

        model = self._get_model(client_id)
        score = model.score_one(x)
        model.learn_one(x)

        self.samples_seen[client_id] += 1
        self.score_history[client_id].append(score)

        if self._is_warmed_up(client_id) and self.samples_seen[client_id] % 25 == 0:
            self._calibrate(client_id)

        return {
            "client_id": client_id,
            "score": score,
            "label": self._classify(client_id, score),
        }
