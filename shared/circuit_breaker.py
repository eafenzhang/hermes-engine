"""Circuit breaker — protect upstream providers from cascading failures.

States: CLOSED → OPEN (N failures in window) → HALF_OPEN (after timeout).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    name: str
    failures: int = 0
    last_failure: float = 0.0
    state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
    opened_at: float = 0.0
    failure_threshold: int = 5
    reset_timeout: float = 30.0  # seconds before CLOSED → HALF_OPEN
    half_open_max: int = 1  # max probe calls in HALF_OPEN


class CircuitBreaker:
    """Thread-safe per-provider circuit breaker."""

    def __init__(self, name: str, threshold: int = 5, reset_sec: float = 30.0):
        self._lock = threading.Lock()
        self._state = CircuitState(
            name=name,
            failure_threshold=threshold,
            reset_timeout=reset_sec,
        )

    @property
    def state(self) -> str:
        return self._state.state

    def record_success(self) -> None:
        with self._lock:
            self._state.failures = 0
            if self._state.state == "HALF_OPEN":
                self._state.state = "CLOSED"
                logger.info("Circuit %s closed (recovery)", self._state.name)

    def record_failure(self) -> None:
        with self._lock:
            s = self._state
            s.failures += 1
            s.last_failure = time.time()
            if s.state == "CLOSED" and s.failures >= s.failure_threshold:
                s.state = "OPEN"
                s.opened_at = time.time()
                logger.warning(
                    "Circuit %s OPEN after %d failures", s.name, s.failures,
                )
            elif s.state == "HALF_OPEN":
                s.state = "OPEN"
                s.opened_at = time.time()
                logger.warning("Circuit %s re-opened (half-open probe failed)", s.name)

    def allow_request(self) -> bool:
        with self._lock:
            s = self._state
            if s.state == "CLOSED":
                return True
            if s.state == "OPEN":
                if time.time() - s.opened_at >= s.reset_timeout:
                    s.state = "HALF_OPEN"
                    logger.info("Circuit %s → HALF_OPEN (probe)", s.name)
                    return True
                return False
            # HALF_OPEN: allow limited probe
            return True


class CircuitBreakerRegistry:
    """Module-level registry of named circuit breakers."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name)
            return self._breakers[name]

    def status(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "name": b._state.name,
                    "state": b._state.state,
                    "failures": b._state.failures,
                }
                for b in self._breakers.values()
            ]


circuits = CircuitBreakerRegistry()
