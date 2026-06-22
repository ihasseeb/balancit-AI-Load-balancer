# Balancit Architecture

## Problem

Cloud-native autoscalers conflate observed traffic with required capacity. When a
service is attacked, observed request volume spikes, and a naive autoscaler responds by
provisioning more capacity to serve that traffic. This amplifies the attack: the victim
pays for infrastructure to process malicious requests, turning a denial-of-service
attempt into an economic denial-of-sustainability problem. Static rate limiters help at
the admission layer but operate without any coordination with capacity planning, and
they cannot distinguish a legitimate traffic surge from an attack.

Balancit addresses this by decoupling observed load from the signal that drives scaling
decisions, using online machine learning to estimate genuine load and to classify
clients, then driving both admission control and autoscaling from that estimate.

## Architecture Diagram in Excalidraw
```https://excalidraw.com/#json=TbzpwVHrYdJ6ukY3hGVhH,B5p6tvUY1JCi2NMmXNvSaQ```

## Problem

Cloud-native autoscalers conflate observed traffic with required capacity. When a
service is attacked, observed request volume spikes, and a naive autoscaler responds by
provisioning more capacity to serve that traffic. This amplifies the attack: the victim
pays for infrastructure to process malicious requests, turning a denial-of-service
attempt into an economic denial-of-sustainability problem. Static rate limiters help at
the admission layer but operate without any coordination with capacity planning, and
they cannot distinguish a legitimate traffic surge from an attack.

Balancit addresses this by decoupling observed load from the signal that drives scaling
decisions, using online machine learning to estimate genuine load and to classify
clients, then driving both admission control and autoscaling from that estimate.

## Components

### Backend services
Two FastAPI microservices with distinct load profiles. service-a is CPU-bound,
service-b is I/O-bound. Both expose Prometheus metrics and propagate the X-Client-ID
header. They exist as realistic, differentiated targets for load and attack traffic.

### ML brain
A standalone service that runs a fixed cycle (every 5 seconds):

1. Feature extraction. Queries Prometheus for each active client and computes three
   features: RPS over a 1-minute window, error rate, and service entropy (Shannon
   entropy across the services the client touches). Only successful requests are
   counted toward RPS, so throttled requests do not register as load.

2. Anomaly detection. A per-client Half-Space Trees model scores each feature vector
   and classifies the client as GENUINE, SUSPICIOUS, or ANOMALY. Each client has an
   independent model with its own warmup and adaptive thresholds.

3. Forecasting. A per-client Holt-Winters (simple exponential smoothing) model predicts
   near-term genuine RPS, learning only from samples classified GENUINE. During an
   attack it continues forecasting the pre-attack baseline.

4. Publication. Writes per-client label, score, forecast, and scaling signal to Redis
   (30s TTL) for the proxy, and publishes per-client gauges to Prometheus for the
   autoscaler. Idle clients publish a scaling signal of zero so the autoscaler responds
   to current state, not stale history.

### Proxy
A reverse proxy in front of both services. It routes by URL prefix and propagates
headers. On every request it reads the client's label from Redis and applies a
token-bucket rate limit for the corresponding tier. It operates in one of three modes
set by BALANCIT_PROXY_MODE:

- none: pass-through, no limiting (the no-protection baseline)
- static: a single fixed token bucket per client (the static rate-limiting baseline)
- ml: per-client tiers driven by the ML label

In ml mode the tiers are, from most to least permissive: GENUINE, UNTRUSTED, SUSPICIOUS,
ANOMALY (blocked). UNTRUSTED is the default for any client without an established label,
including those still in warmup. If Redis is unreachable the proxy fails open to
UNTRUSTED, so a dependency outage degrades gracefully rather than blocking all traffic.

### Autoscaler
A Kubernetes Horizontal Pod Autoscaler per service. It scales on ml_service_signal, a
per-service sum of per-client forecasts, exposed through a Prometheus recording rule and
the Prometheus Adapter as an external metric. Because the signal reflects forecasted
genuine load (not raw observed traffic), attack volume does not inflate the scaling
decision.

## The unifying idea

Both enforcement consumers are driven by the same ML brain, but at different
granularities. The proxy consumes per-client labels because throttling is a per-request
decision. The autoscaler consumes per-service aggregated forecasts because scaling is a
per-service decision. One analysis pipeline produces two outputs (a label and a
forecast) that protect the system in two complementary ways: throttling individual bad
actors at the door, and provisioning capacity only for genuine demand.

## Trust lifecycle of a client

1. Unknown / warmup. A new identity has no model baseline. It is throttled at the
   UNTRUSTED tier so it cannot cause damage while the system has no information about it.
   During this phase autoscaling falls back to raw observed RPS, since no forecast
   exists yet.

2. Classified. After enough samples, the client is labeled GENUINE, SUSPICIOUS, or
   ANOMALY, and the proxy applies the corresponding tier. The forecast begins
   contributing to the scaling signal.

3. Continuously monitored. Classification updates every cycle. A client that deviates
   from its established baseline is re-classified immediately, so trust can be revoked
   as quickly as it was granted.

## Failure modes and resilience

- Redis unreachable: proxy fails open to UNTRUSTED; no crash.
- ML service restart: in-memory models reset; clients re-warm from cold. Steady-state
  behavior is unaffected once warmup completes.
- Stale signals: idle clients publish a zero scaling signal, and Redis entries expire
  via TTL, so the system tracks current state rather than recent history.
- Sustained state accumulation: HST score history accumulates during IDLE periods
  between client sessions, causing threshold drift in long-running deployments.
  Periodic pruning of IDLE client histories is the recommended mitigation.

## Technology

Python, FastAPI, the River library (Half-Space Trees, Holt-Winters), Redis, Prometheus, Grafana, OpenTelemetry, the Prometheus Adapter, and Kubernetes (kind for local deployment).
