from __future__ import annotations

import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class SearchPerfTrace:
    route: str
    query_hash: str | None = None
    started: float = field(default_factory=time.perf_counter)
    stage_durations_ms: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    stage_counts: Counter[str] = field(default_factory=Counter)
    db_query_count: int = 0
    db_query_operations: Counter[str] = field(default_factory=Counter)
    db_connection_checkout_count: int = 0
    candidate_count: int = 0
    record_count_scored: int = 0
    result_count: int = 0
    full_scan: bool = False
    ranking_config_version: str | None = None

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.stage_durations_ms[name] += elapsed_ms
            self.stage_counts[name] += 1

    def record_db_query(self, operation: str = "execute") -> None:
        self.db_query_count += 1
        self.db_query_operations[operation] += 1

    def record_connection_checkout(self) -> None:
        self.db_connection_checkout_count += 1

    def finish(self) -> dict:
        total_ms = (time.perf_counter() - self.started) * 1000.0
        stages = {
            name: round(ms, 3)
            for name, ms in sorted(self.stage_durations_ms.items())
        }
        return {
            "route": self.route,
            "query_hash": self.query_hash,
            "total_ms": round(total_ms, 3),
            "stages_ms": stages,
            "stage_counts": dict(self.stage_counts),
            "db_query_count": self.db_query_count,
            "db_query_operations": dict(self.db_query_operations),
            "db_connection_checkout_count": self.db_connection_checkout_count,
            "candidate_count": self.candidate_count,
            "record_count_scored": self.record_count_scored,
            "result_count": self.result_count,
            "full_scan": self.full_scan,
            "ranking_config_version": self.ranking_config_version,
        }


_current_trace: ContextVar[SearchPerfTrace | None] = ContextVar("ma3_search_perf_trace", default=None)


def current_trace() -> SearchPerfTrace | None:
    return _current_trace.get()


@contextmanager
def search_perf_trace(route: str, query_hash: str | None = None) -> Iterator[SearchPerfTrace]:
    trace = SearchPerfTrace(route=route, query_hash=query_hash)
    token = _current_trace.set(trace)
    try:
        yield trace
    finally:
        _current_trace.reset(token)


@contextmanager
def perf_stage(name: str) -> Iterator[None]:
    trace = current_trace()
    if trace is None:
        yield
        return
    with trace.stage(name):
        yield


def record_db_query(operation: str = "execute") -> None:
    trace = current_trace()
    if trace is not None:
        trace.record_db_query(operation)


def record_connection_checkout() -> None:
    trace = current_trace()
    if trace is not None:
        trace.record_connection_checkout()
