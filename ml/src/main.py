import time
from .feature_extractor import FeatureExtractor
from .detector import HSTDetector
from .forecaster import LoadForecaster
from .publisher import Publisher
from .config import settings


def main():
    print("[main] ML service starting (per-client mode)...", flush=True)
    extractor = FeatureExtractor()
    detector = HSTDetector()
    forecaster = LoadForecaster()
    publisher = Publisher()

    while True:
        features = extractor.extract()
        if not features:
            print("[main] No active clients.", flush=True)
        else:
            for f in features:
                detect_result = detector.process(f)
                forecast_result = forecaster.update_and_forecast(
                    client_id=f["client_id"],
                    rps=f["rps"],
                    label=detect_result["label"],
                )

                publisher.publish(
                    client_id=f["client_id"],
                    service=f["service"],
                    rps=f["rps"],
                    score=detect_result["score"],
                    label=detect_result["label"],
                    forecast=forecast_result["forecast_30s"],
                )

                fc = forecast_result["forecast_30s"]
                fc_str = f"{fc:.4f}" if fc is not None else "warmup"

                print(
                    f"[ml] client={f['client_id']} "
                    f"rps={f['rps']} "
                    f"score={detect_result['score']:.4f} "
                    f"label={detect_result['label']} "
                    f"forecast_30s={fc_str}",
                    flush=True,
                )
        time.sleep(settings.scrape_interval)


if __name__ == "__main__":
    main()
