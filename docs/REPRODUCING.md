# Reproducing Balancit Experiments

This document describes how to reproduce the experiments from the Balancit evaluation.

## Prerequisites

- Docker
- Kind (Kubernetes in Docker)
- kubectl
- helm
- Python 3.11+
- make

## Cluster Setup

```bash
# create cluster, build, make deployments, apply rules with this single command
make bootstrap
```

## Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n balancit
kubectl get pods -n monitoring

# Check HPA is configured
make hpa-status
```

## Running Experiments

### Prerequisites
Open two terminals:

**Terminal 1: Port forwards (keep running):**
```bash
./experiments/forward.sh
```

**Terminal 2: Experiments:**
```bash
ulimit -n 65536
cd balancit
source load/.venv/bin/activate
pip install locust
```

### Full Experiment Matrix

```bash
# None mode
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline none 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline none 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline none 3

kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack none 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack none 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack none 3

kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd none 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd none 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd none 3

# Static mode
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline static 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline static 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline static 3

kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack static 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack static 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack static 3

kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd static 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd static 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd static 3

# ML mode — restart ML service first for clean state
kubectl rollout restart deployment/ml-service -n balancit
kubectl rollout status deployment/ml-service -n balancit
kubectl exec -it deployment/redis -n balancit -- redis-cli FLUSHALL

# Warmup run (throwaway)
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline ml 0

# Baseline ml
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline ml 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline ml 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh baseline ml 3

# Attack warmup (throwaway)
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack ml 0

# Attack ml
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack ml 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack ml 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh attack ml 3

# Flashcrowd ml
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd ml 1
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd ml 2
kubectl scale deployment service-a -n balancit --replicas=1
./experiments/run.sh flashcrowd ml 3
```

## Generating Plots

```bash
source ./experiments/.venv/bin/activate
pip install matplotlib
mkdir plots
python experiments/plot.py --results results/ --out plots/
```

## Experiment Parameters

| Parameter | Value |
|---|---|
| Users | 40 (29 genuine + 11 attackers in attack scenario) |
| Duration | 8 minutes per run |
| Repeats | 3 per scenario/mode combination |
| Scenarios | baseline, attack, flashcrowd |
| Modes | none, static, ml |
| Total runs | 27 + 4 warmup runs |

## Notes

- ML mode preserves inter-run state to simulate continuous production operation
- Scale down service-a before each run to ensure clean starting replica count
- forward.sh must be running throughout all experiments
- Results stored
