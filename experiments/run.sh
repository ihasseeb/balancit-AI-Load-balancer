#!/usr/bin/env bash
#
# Balancit experiment runner. One clean, reproducible run per invocation.
#
# Usage:
#   ./experiments/run.sh <scenario> <mode> <rep> [duration_min] [users]
#
#   scenario : baseline | attack | flashcrowd   (selects the locust load shape)
#   mode     : none | static | ml               (proxy defense mode)
#   rep      : repetition number, e.g. 1
#   duration : run length in minutes (default 8)
#   users    : locust user count (default 40)
#
# Example:
#   ./experiments/run.sh attack ml 1
#
# Prerequisites (must already be running in another terminal):
#   ./experiments/forward.sh      (proxy 8080 + prometheus 9090, self-healing)
#   ulimit -n 65536               (in the shell that runs this script)
#
# Assumes the locustfile exposes a SCENARIO env var to pick the load shape.

set -euo pipefail

SCENARIO="${1:?need scenario: baseline|attack|flashcrowd}"
MODE="${2:?need mode: none|static|ml}"
REP="${3:?need rep number}"
DURATION_MIN="${4:-8}"
USERS="${5:-40}"

NS="balancit"
PROXY_URL="http://localhost:8080"
PROM_URL="http://localhost:9090"
OUTDIR="results/${SCENARIO}_${MODE}_run${REP}"
DURATION_SEC=$(( DURATION_MIN * 60 ))
COLLECT_SEC=$(( DURATION_SEC + 30 ))

echo "=============================================="
echo " Run: scenario=$SCENARIO mode=$MODE rep=$REP"
echo " duration=${DURATION_MIN}m users=$USERS"
echo " output -> $OUTDIR"
echo "=============================================="

mkdir -p "$OUTDIR"

# --- 1. Preflight: is the load path alive? -------------------------------------
echo "[1/7] Preflight: checking proxy reachability"
if ! curl -sf -o /dev/null -H "X-Client-ID: preflight" "$PROXY_URL/service-a/api/light"; then
  echo "  ABORT: proxy not reachable at $PROXY_URL. Is forward.sh running?" >&2
  exit 1
fi
if ! curl -sf -o /dev/null "$PROM_URL/api/v1/query?query=up"; then
  echo "  ABORT: prometheus not reachable at $PROM_URL. Is forward.sh running?" >&2
  exit 1
fi
echo "  ok: proxy and prometheus reachable"

# --- 2. Set the proxy mode -----------------------------------------------------
if [[ "$MODE" == "ml" ]]; then
  echo "[2/7] Setting proxy mode to '$MODE' (no restart for ml mode)"
  kubectl set env deployment/proxy -n "$NS" "BALANCIT_PROXY_MODE=$MODE" >/dev/null
  sleep 5
else
  echo "[2/7] Setting proxy mode to '$MODE'"
  kubectl set env deployment/proxy -n "$NS" "BALANCIT_PROXY_MODE=$MODE" >/dev/null
  kubectl rollout status deployment/proxy -n "$NS" --timeout=120s
fi
ACTUAL=$(kubectl get deployment proxy -n "$NS" \
  -o jsonpath='{range .spec.template.spec.containers[0].env[?(@.name=="BALANCIT_PROXY_MODE")]}{.value}{end}')
if [[ "$ACTUAL" != "$MODE" ]]; then
  echo "  ABORT: mode is '$ACTUAL', expected '$MODE'" >&2
  exit 1
fi
echo "  ok: mode confirmed '$ACTUAL'"

# --- 3. Reset ML state (skipped for ml mode to preserve warmup history) --------
if [[ "$MODE" != "ml" ]]; then
  echo "[3/7] Restarting ML service for a clean per-client baseline"
  kubectl rollout restart deployment/ml-service -n "$NS" >/dev/null
  kubectl rollout status deployment/ml-service -n "$NS" --timeout=120s
  echo "  ok: ml-service fresh"
else
  echo "[3/7] Skipping ML service restart (ml mode: preserving client history)"
fi

# --- 4. Wait for the cluster to settle to baseline -----------------------------
echo "[4/7] Waiting for service-a to settle to 1 replica (max 10 min)"
for _ in $(seq 1 120); do
  REPL=$(kubectl get deployment service-a -n "$NS" -o jsonpath='{.status.readyReplicas}')
  REPL=${REPL:-0}
  if [[ "$REPL" -le 1 ]]; then
    echo "  ok: service-a at $REPL replica"
    break
  fi
  sleep 5
done

# --- 5. Start the collector (background) ---------------------------------------
echo "[5/7] Starting collector for ${COLLECT_SEC}s"
python experiments/collector.py \
  --out "$OUTDIR/metrics" --interval 5 --duration "$COLLECT_SEC" \
  > "$OUTDIR/collector.log" 2>&1 &
COLLECTOR_PID=$!
sleep 2
if ! kill -0 "$COLLECTOR_PID" 2>/dev/null; then
  echo "  ABORT: collector failed to start, see $OUTDIR/collector.log" >&2
  exit 1
fi
echo "  ok: collector running (pid $COLLECTOR_PID)"

# --- 6. Run Locust (foreground, blocks until done) -----------------------------
echo "[6/7] Running Locust: $SCENARIO, ${DURATION_MIN}m, $USERS users"
SCENARIO="$SCENARIO" locust -f load/locustfile.py --headless \
  -u "$USERS" -r 5 -t "${DURATION_MIN}m" \
  --host "$PROXY_URL" \
  --csv "$OUTDIR/locust" \
  --only-summary \
  || echo "  warn: locust exited non-zero (check $OUTDIR)"

# --- 7. Stop the collector and finish ------------------------------------------
set +e
echo "[7/7] Stopping collector"
if kill -0 "$COLLECTOR_PID" 2>/dev/null; then
  sleep 10
  kill -INT "$COLLECTOR_PID" 2>/dev/null
  wait "$COLLECTOR_PID" 2>/dev/null
fi

cat > "$OUTDIR/run_meta.txt" <<EOF
scenario=$SCENARIO
mode=$MODE
rep=$REP
duration_min=$DURATION_MIN
users=$USERS
proxy_mode_confirmed=$ACTUAL
timestamp=$(date -Is)
EOF

echo "=============================================="
echo " Done. Outputs in $OUTDIR"
echo "   metrics_timeseries.csv, metrics_clients.csv"
echo "   locust_stats.csv, locust_stats_history.csv"
echo "   run_meta.txt, collector.log"
echo "=============================================="
