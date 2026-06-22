"""
Balancit load generation, scenario-aware.

The SCENARIO environment variable selects which user populations are active:

  baseline    : genuine users only (no attack). Tests normal operation.
  attack      : genuine users plus an attacker population hammering one endpoint.
  flashcrowd  : a larger genuine population, no attacker. Tests whether a legitimate
                surge is handled without being mistaken for an attack.

Each spawned user gets a UNIQUE client id (no collisions, so genuine users do not
self-throttle by sharing an identity). Genuine users pace themselves and spread across
endpoints (high entropy). Attackers send as fast as the limiter allows against one
endpoint (low entropy).

Tune the attacker identity count with ATTACKER_IDS (default 3). A small number gives
the clean per-client amplification story; a large number exercises the
identity-multiplication weakness.

Run via the runner (sets SCENARIO for you), or directly:
  SCENARIO=attack locust -f load/locustfile.py --headless -u 40 -r 5 -t 8m \
      --host http://localhost:8080
"""

import itertools
import os
import random

from locust import HttpUser, task, between, constant


SCENARIO = os.environ.get("SCENARIO", "baseline").lower()
ATTACKER_IDS = int(os.environ.get("ATTACKER_IDS", "3"))

# Unique genuine identities, one per spawned user.
_gen_counter = itertools.count(1)
# A bounded pool of attacker identities (shared, to model a fixed attacker fleet).
_attacker_pool = [f"atk-{i:03d}" for i in range(max(1, ATTACKER_IDS))]


class GenuineUser(HttpUser):
    """Legitimate user: paced, spread across both services."""
    wait_time = between(0.4, 0.8)

    def on_start(self):
        self.client_id = f"gen-{next(_gen_counter):03d}"

    def _h(self):
        return {"X-Client-ID": self.client_id}

    @task(4)
    def cpu(self):
        self.client.get("/service-a/api/cpu", headers=self._h(),
                        name="genuine /service-a/api/cpu")

    @task(3)
    def light(self):
        self.client.get("/service-a/api/light", headers=self._h(),
                        name="genuine /service-a/api/light")

    @task(3)
    def io(self):
        self.client.get("/service-b/api/io", headers=self._h(),
                        name="genuine /service-b/api/io")


class AttackerUser(HttpUser):
    """Attacker: no pacing, single endpoint, identity drawn from a fixed pool."""
    wait_time = constant(0)

    def on_start(self):
        self.client_id = random.choice(_attacker_pool)

    def _h(self):
        return {"X-Client-ID": self.client_id}

    @task
    def flood(self):
        self.client.get("/service-a/api/cpu", headers=self._h(),
                        name="attacker /service-a/api/cpu")


# Select which user classes Locust spawns, based on the scenario.
if SCENARIO in ("baseline", "flashcrowd"):
    GenuineUser.weight = 1
    del AttackerUser
elif SCENARIO == "attack":
    GenuineUser.weight = 5
    AttackerUser.weight = 2
else:
    raise ValueError("unknown SCENARIO '%s' (expected baseline | attack | flashcrowd)"
                     % SCENARIO)
