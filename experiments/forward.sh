#!/usr/bin/env bash
# Self-healing port-forwards for experiments.
# Restarts a forward immediately if it drops, so heavy load can't leave it dead.
set -u

forward() {
  local ns="$1" svc="$2" ports="$3"
  while true; do
    echo "[forward] $svc $ports starting"
    kubectl port-forward -n "$ns" "svc/$svc" "$ports" >/dev/null 2>&1
    echo "[forward] $svc $ports dropped, restarting in 1s"
    sleep 1
  done
}

forward balancit proxy 8080:8080 &
forward monitoring prometheus-kube-prometheus-prometheus 9090:9090 &

echo "Forwards running (proxy 8080, prometheus 9090). Ctrl+C to stop all."
wait
