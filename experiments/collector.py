"""
Balancit experiment results collector.

Polls Prometheus and the Kubernetes API on a fixed interval during an experiment run
and writes two CSVs:

  <out>_timeseries.csv  one row per poll: replicas and ML signal per service, plus
                        aggregate served/throttled request counts.
  <out>_clients.csv     one row per client per poll: per-client served (200) and
                        throttled (429) totals, label-style breakdown by behavior.

Metrics used (confirmed present in this deployment):
  ml_service_signal{service=...}          -> HPA driver, per service
  ml_client_score{client_id=...}          -> per-client anomaly score (if exported)
  proxy_requests_total{client_id,service,status}  -> per-client request counter

Replica counts come from kubectl (the autoscaling evidence Prometheus does not hold
directly in a convenient form).

Usage:
  # Prometheus must be reachable (port-forward in another terminal):
  #   kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
  python collector.py --out results/attack_ml_run1 --interval 5 --duration 600

Stop early with Ctrl+C; partial CSVs are still written.
"""

import argparse
import csv
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request


PROM = "http://localhost:9090"
NAMESPACE = "balancit"
SERVICES = ["service-a", "service-b"]


def prom_query(expr):
    """Run an instant PromQL query, return the list of result series (may be empty)."""
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.load(resp)
        if data.get("status") != "success":
            return []
        return data["data"]["result"]
    except Exception as e:
        print(f"  [warn] prom query failed ({expr}): {e}", file=sys.stderr)
        return []


def scalar_by_service(expr, label="service"):
    """Return {service_value: float} from a query that is labeled by `service`."""
    out = {}
    for series in prom_query(expr):
        key = series["metric"].get(label, "?")
        try:
            out[key] = float(series["value"][1])
        except (KeyError, ValueError, IndexError):
            pass
    return out


def get_replicas():
    """Return {service: ready_replica_count} via kubectl."""
    out = {}
    for svc in SERVICES:
        try:
            res = subprocess.run(
                ["kubectl", "get", "deployment", svc, "-n", NAMESPACE,
                 "-o", "jsonpath={.status.readyReplicas}"],
                capture_output=True, text=True, timeout=10,
            )
            val = res.stdout.strip()
            out[svc] = int(val) if val else 0
        except Exception as e:
            print(f"  [warn] kubectl replicas failed ({svc}): {e}", file=sys.stderr)
            out[svc] = -1
    return out


def get_per_client_requests():
    """
    Return {(client_id, service, status): count} from proxy_requests_total.
    These are cumulative counters; the analysis step diffs them across the run.
    """
    out = {}
    for series in prom_query("proxy_requests_total"):
        m = series["metric"]
        cid = m.get("client_id", "?")
        svc = m.get("service", "?")
        status = m.get("status", "?")
        try:
            out[(cid, svc, status)] = float(series["value"][1])
        except (ValueError, IndexError):
            pass
    return out


def classify(cid):
    """Tag a client id as genuine / attacker / other based on the load-gen naming."""
    if cid.startswith("gen-"):
        return "genuine"
    if cid.startswith("atk-"):
        return "attacker"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output path prefix")
    ap.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    ap.add_argument("--duration", type=float, default=600.0, help="total seconds to run")
    args = ap.parse_args()

    ts_path = f"{args.out}_timeseries.csv"
    cl_path = f"{args.out}_clients.csv"

    ts_file = open(ts_path, "w", newline="")
    cl_file = open(cl_path, "w", newline="")
    ts_writer = csv.writer(ts_file)
    cl_writer = csv.writer(cl_file)

    ts_writer.writerow([
        "t", "wall_clock",
        "replicas_service_a", "replicas_service_b",
        "signal_service_a", "signal_service_b",
        "served_total", "throttled_total",
        "served_genuine", "throttled_genuine",
        "served_attacker", "throttled_attacker",
    ])
    cl_writer.writerow([
        "t", "client_id", "kind", "service", "served_200", "throttled_429", "score",
    ])

    print(f"Collecting every {args.interval}s for {args.duration}s")
    print(f"  timeseries -> {ts_path}")
    print(f"  clients    -> {cl_path}")

    start = time.time()
    try:
        while True:
            t = time.time() - start
            if t > args.duration:
                break
            wall = time.strftime("%H:%M:%S")

            replicas = get_replicas()
            signal = scalar_by_service("ml_service_signal")
            scores = {}
            for s in prom_query("ml_client_score"):
                cid = s["metric"].get("client_id", "?")
                try:
                    scores[cid] = float(s["value"][1])
                except (ValueError, IndexError):
                    pass
            reqs = get_per_client_requests()

            # Aggregate served/throttled, split by kind.
            agg = {
                ("served", "all"): 0.0, ("throttled", "all"): 0.0,
                ("served", "genuine"): 0.0, ("throttled", "genuine"): 0.0,
                ("served", "attacker"): 0.0, ("throttled", "attacker"): 0.0,
            }
            per_client = {}
            for (cid, svc, status), count in reqs.items():
                kind = classify(cid)
                bucket = "served" if status == "200" else (
                    "throttled" if status == "429" else None)
                if bucket is None:
                    continue
                agg[(bucket, "all")] += count
                if kind in ("genuine", "attacker"):
                    agg[(bucket, kind)] += count
                key = (cid, svc)
                if key not in per_client:
                    per_client[key] = {"200": 0.0, "429": 0.0, "kind": kind}
                per_client[key][status if status in ("200", "429") else "200"] += count

            ts_writer.writerow([
                round(t, 1), wall,
                replicas.get("service-a", -1), replicas.get("service-b", -1),
                round(signal.get("service-a", 0.0), 4),
                round(signal.get("service-b", 0.0), 4),
                round(agg[("served", "all")]), round(agg[("throttled", "all")]),
                round(agg[("served", "genuine")]), round(agg[("throttled", "genuine")]),
                round(agg[("served", "attacker")]), round(agg[("throttled", "attacker")]),
            ])
            ts_file.flush()

            for (cid, svc), d in sorted(per_client.items()):
                cl_writer.writerow([
                    round(t, 1), cid, d["kind"], svc,
                    round(d["200"]), round(d["429"]),
                    round(scores.get(cid, float("nan")), 4),
                ])
            cl_file.flush()

            print(f"  t={t:6.1f}s  a={replicas.get('service-a','?')} "
                  f"b={replicas.get('service-b','?')}  "
                  f"sig_a={signal.get('service-a',0):.2f}  "
                  f"served={round(agg[('served','all')])} "
                  f"throttled={round(agg[('throttled','all')])}")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped early; partial data written.")
    finally:
        ts_file.close()
        cl_file.close()
        print(f"Done. Wrote {ts_path} and {cl_path}")


if __name__ == "__main__":
    main()
