from collections import defaultdict
from river import time_series
from .config import settings


class LoadForecaster:
    """One forecaster per client. Learns only from GENUINE samples."""

    def __init__(self):
        self.models: dict = {}
        self.samples_seen: dict = defaultdict(int)

    def _new_model(self):
        return time_series.HoltWinters(alpha=0.3, beta=0.0)

    def _get_model(self, client_id: str):
        if client_id not in self.models:
            self.models[client_id] = self._new_model()
        return self.models[client_id]

    def update_and_forecast(self, client_id: str, rps: float, label: str) -> dict:
        model = self._get_model(client_id)

        if label == "GENUINE":
            model.learn_one(rps)
            self.samples_seen[client_id] += 1

        if self.samples_seen[client_id] < settings.forecaster_warmup_samples:
            return {"client_id": client_id, "forecast_30s": None, "warmed_up": False}

        try:
            forecast = model.forecast(horizon=settings.forecast_horizon)
            forecast_avg = max(0.0, sum(forecast) / len(forecast))
        except Exception as e:
            print(f"[forecaster] {client_id} forecast failed: {e}", flush=True)
            forecast_avg = None

        return {"client_id": client_id, "forecast_30s": forecast_avg, "warmed_up": True}
