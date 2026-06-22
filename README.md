# Balancit

An AI-driven adaptive traffic management framework for Kubernetes that combines online anomaly detection and short-horizon load forecasting to protect backend microservices from DDoS and abnormal traffic while preserving quality of service for legitimate users.

## What it does

Balancit sits between clients and services, classifying per-client traffic behavior in real time using Half-Space Trees (HST) for anomaly detection and Holt-Winters Exponential Smoothing (HWES) for load forecasting. It throttles anomalous clients surgically while allowing genuine users through, and drives Kubernetes autoscaling from forecasted genuine load rather than raw observed traffic, decoupling scaling decisions from attack volume.

## Components

| Component | Role |
|---|---|
| Proxy | FastAPI reverse proxy, per-client token-bucket rate limiting |
| ML Brain | Feature extraction, HST anomaly detection, HWES forecasting |
| Redis | Label store, proxy reads per-client labels on every request |
| Prometheus | Metrics substrate, ML brain reads traffic, publishes scaling signal |
| HPA | Scales services on `ml_service_signal` (forecasted genuine load) |
| service-a | CPU-bound backend (hash computation, ~100ms) |
| service-b | I/O-bound backend (simulated I/O wait, ~150ms) |

## Proxy Modes

| Mode | Behavior |
|---|---|
| `none` | Pass-through, no limiting (unprotected baseline) |
| `static` | Fixed token bucket per client (static rate-limiting baseline) |
| `ml` | Per-client tiers driven by ML label |

## ML Labels and Rate Tiers

| Label | Meaning | Rate Limit |
|---|---|---|
| UNTRUSTED | New or unknown client | 2 rps |
| GENUINE | Normal behavior confirmed | 10 rps |
| SUSPICIOUS | Elevated anomaly score | 1 rps |
| ANOMALY | Attack pattern detected | Blocked |

## Evaluation Results

Evaluated across 27 controlled experiments (3 scenarios × 3 modes × 3 repeats):

Balancit is the only mode that simultaneously achieves the highest attacker throttle rate (96.6%) and the lowest genuine user latency under attack (497ms). Under baseline conditions, Balancit also outperforms both baselines (110ms vs 143ms static, 173ms none) due to proactive load signal filtering.

## Quick Start

### Prerequisites
- Docker
- Kind
- kubectl
- Python 3.11+
- make

### Deploy

See [REPRODUCING.md](./docs/REPRODUCING.md) .

### Run Experiments

See [REPRODUCING.md](./docs/REPRODUCING.md) .

### Generate Plots

See [REPRODUCING.md](./docs/REPRODUCING.md) for the full experiment matrix.

## Key Findings

- **96.6% attacker throttle rate** vs 91.3% static and 0% unprotected (balancit's attacker throttle rate increases with longer tests)
- **497ms genuine p99 under attack** vs 650ms unprotected and 727ms static
- **110ms genuine p99 at baseline**  better than both static (143ms) and unprotected (173ms)
- Static rate limiting degrades under sustained attack (genuine p99 increases across runs); Balancit maintains consistent protection
- Zero false positive attack detection in flashcrowd scenario (all legitimate surge clients correctly labeled GENUINE)

## Reproducing

See [REPRODUCING.md](./docs/REPRODUCING.md).

## Technology

Python, FastAPI, River (Half-Space Trees, Holt-Winters), Redis, Prometheus, Grafana, OpenTelemetry, Prometheus Adapter, Kubernetes (Kind)

