#!/usr/bin/env python3
"""
Balancit experiment results plotter.
Reads locust_stats.csv and metrics_timeseries.csv from results/
and generates thesis-ready plots.

Usage:
    python experiments/plot.py --results results/ --out plots/
"""

import argparse
import os
import csv
import statistics
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

SCENARIOS = ["baseline", "attack", "flashcrowd"]
MODES = ["none", "static", "ml"]
REPS = [1, 2, 3]

MODE_COLORS = {
    "none": "#e74c3c",
    "static": "#f39c12",
    "ml": "#27ae60",
}
MODE_LABELS = {
    "none": "No Protection",
    "static": "Static Rate Limit",
    "ml": "Balancit (ML)",
}


def load_locust_stats(results_dir: Path, scenario: str, mode: str, rep: int) -> dict | None:
    path = results_dir / f"{scenario}_{mode}_run{rep}" / "locust_stats.csv"
    if not path.exists():
        return None
    rows = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            rows[row["Name"]] = row
    return rows


def load_timeseries(results_dir: Path, scenario: str, mode: str, rep: int) -> list[dict] | None:
    path = results_dir / f"{scenario}_{mode}_run{rep}" / "metrics_timeseries.csv"
    if not path.exists():
        return None
    with open(path) as f:
        return list(csv.DictReader(f))


def get_attacker_throttle_rate(stats: dict) -> float:
    """Fraction of attacker requests that were throttled (429)."""
    for name, row in stats.items():
        if "attacker" in name:
            total = int(row["Request Count"])
            failed = int(row["Failure Count"])
            if total > 0:
                return failed / total
    return 0.0


def get_genuine_p99(stats: dict, endpoint: str = "cpu") -> float:
    """p99 latency for genuine users on the given endpoint."""
    for name, row in stats.items():
        if "genuine" in name and endpoint in name:
            return float(row["99%"])
    return 0.0


def get_genuine_failure_rate(stats: dict) -> float:
    """Fraction of genuine requests that failed."""
    total = failed = 0
    for name, row in stats.items():
        if "genuine" in name:
            total += int(row["Request Count"])
            failed += int(row["Failure Count"])
    return failed / total if total > 0 else 0.0


def avg(values: list) -> float:
    return statistics.mean(values) if values else 0.0


def collect_metric(results_dir, scenario, mode, fn):
    values = []
    for rep in REPS:
        stats = load_locust_stats(results_dir, scenario, mode, rep)
        if stats:
            values.append(fn(stats))
    return avg(values)


def plot_attacker_throttle(results_dir: Path, out_dir: Path):
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(MODES))
    width = 0.35

    throttle_rates = [
        collect_metric(results_dir, "attack", mode,
                       get_attacker_throttle_rate) * 100
        for mode in MODES
    ]

    bars = ax.bar(x, throttle_rates, width=0.5,
                  color=[MODE_COLORS[m] for m in MODES],
                  edgecolor="white", linewidth=1.5)

    for bar, val in zip(bars, throttle_rates):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                f"{val:.1f}%", ha="center", va="bottom",
                fontsize=11, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels([MODE_LABELS[m] for m in MODES], fontsize=11)
    ax.set_ylabel("Attacker Requests Throttled (%)", fontsize=11)
    ax.set_title("Attack Scenario: Attacker Throttle Rate by Mode", fontsize=13)
    ax.set_ylim(0, 110)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    path = out_dir / "attacker_throttle_rate.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  saved {path}")


def plot_genuine_p99(results_dir: Path, out_dir: Path):
    fig, axes = plt.subplots(1, 3, figsize=(14, 5), sharey=False)

    for ax, scenario in zip(axes, SCENARIOS):
        p99s = [
            collect_metric(results_dir, scenario, mode,
                           lambda s: get_genuine_p99(s, "cpu"))
            for mode in MODES
        ]
        x = np.arange(len(MODES))
        bars = ax.bar(x, p99s, width=0.5,
                      color=[MODE_COLORS[m] for m in MODES],
                      edgecolor="white", linewidth=1.5)

        for bar, val in zip(bars, p99s):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 5,
                    f"{val:.0f}ms", ha="center", va="bottom",
                    fontsize=10, fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES],
                           fontsize=9, rotation=10)
        ax.set_ylabel("p99 Latency (ms)", fontsize=10)
        ax.set_title(scenario.capitalize(), fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle("Genuine User p99 Latency by Scenario and Mode", fontsize=13)
    plt.tight_layout()
    path = out_dir / "genuine_p99_latency.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  saved {path}")


def plot_genuine_failure_rate(results_dir: Path, out_dir: Path):
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    for ax, scenario in zip(axes, SCENARIOS):
        rates = [
            collect_metric(results_dir, scenario, mode,
                           get_genuine_failure_rate) * 100
            for mode in MODES
        ]
        x = np.arange(len(MODES))
        bars = ax.bar(x, rates, width=0.5,
                      color=[MODE_COLORS[m] for m in MODES],
                      edgecolor="white", linewidth=1.5)

        for bar, val in zip(bars, rates):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.02,
                    f"{val:.2f}%", ha="center", va="bottom",
                    fontsize=10, fontweight="bold")

        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES],
                           fontsize=9, rotation=10)
        ax.set_ylabel("Genuine Failure Rate (%)", fontsize=10)
        ax.set_title(scenario.capitalize(), fontsize=12)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle("Genuine User Failure Rate by Scenario and Mode", fontsize=13)
    plt.tight_layout()
    path = out_dir / "genuine_failure_rate.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  saved {path}")


def plot_replica_timeseries(results_dir: Path, out_dir: Path):
    """Plot replica count over time for attack scenario across modes."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)

    for ax, mode in zip(axes, MODES):
        for rep in REPS:
            ts = load_timeseries(results_dir, "attack", mode, rep)
            if not ts:
                continue
            t = [float(r["t"]) for r in ts]
            replicas = [int(r["replicas_service_a"]) for r in ts]
            ax.plot(t, replicas, alpha=0.5, linewidth=1.5,
                    color=MODE_COLORS[mode],
                    label=f"run {rep}")

        ax.set_title(MODE_LABELS[mode], fontsize=11)
        ax.set_xlabel("Time (s)", fontsize=10)
        ax.set_ylabel("service-a Replicas", fontsize=10)
        ax.set_ylim(0, 16)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)

    fig.suptitle("Attack Scenario: service-a Replica Count Over Time", fontsize=13)
    plt.tight_layout()
    path = out_dir / "replica_timeseries_attack.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  saved {path}")


def plot_throttle_timeseries(results_dir: Path, out_dir: Path):
    """Plot attacker vs genuine throttled requests over time for attack ml."""
    fig, ax = plt.subplots(figsize=(10, 5))

    for rep in REPS:
        ts = load_timeseries(results_dir, "attack", "ml", rep)
        if not ts:
            continue
        t = [float(r["t"]) for r in ts]
        throttled_atk = [float(r["throttled_attacker"]) for r in ts]
        throttled_gen = [float(r["throttled_genuine"]) for r in ts]

        ax.plot(t, throttled_atk, color="#e74c3c", alpha=0.6,
                linewidth=1.5, label=f"Attacker throttled (run {rep})")
        ax.plot(t, throttled_gen, color="#3498db", alpha=0.6,
                linewidth=1.5, linestyle="--",
                label=f"Genuine throttled (run {rep})")

    ax.set_xlabel("Time (s)", fontsize=11)
    ax.set_ylabel("Cumulative Throttled Requests", fontsize=11)
    ax.set_title("Attack ML: Attacker vs Genuine Throttling Over Time", fontsize=13)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2)

    plt.tight_layout()
    path = out_dir / "throttle_timeseries_attack_ml.png"
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  saved {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results/", type=Path)
    ap.add_argument("--out", default="plots/", type=Path)
    args = ap.parse_args()

    args.out.mkdir(exist_ok=True)
    print(f"Reading from {args.results}, writing to {args.out}")

    plot_attacker_throttle(args.results, args.out)
    plot_genuine_p99(args.results, args.out)
    plot_genuine_failure_rate(args.results, args.out)
    plot_replica_timeseries(args.results, args.out)
    plot_throttle_timeseries(args.results, args.out)

    print("\nDone. Plots:")
    for f in sorted(args.out.glob("*.png")):
        print(f"  {f}")


if __name__ == "__main__":
    main()
