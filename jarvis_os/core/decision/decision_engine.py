from __future__ import annotations

import threading
from typing import Optional

from .decision_policy import DecisionPolicy, DefaultDecisionPolicy
from .models import DecisionContext, DecisionResult



class DecisionEngine:
    """Deterministic decision router.

    Thread-safe: DecisionEngine holds only a policy reference and uses a lock
    to guard any potentially stateful policies.

    Responsibilities:
      - decide() returns a DecisionResult with a DecisionType and reason.
      - never executes tools, never calls infrastructure, never performs AI reasoning.
    """

    def __init__(self, policy: Optional[DecisionPolicy] = None) -> None:
        self._policy = policy or DefaultDecisionPolicy()
        self._lock = threading.Lock()

    def decide(self, ctx: DecisionContext) -> DecisionResult:
        with self._lock:
            return self._policy.decide(ctx)

