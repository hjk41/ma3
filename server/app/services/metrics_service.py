from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self.http_requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self.http_durations: dict[tuple[str, str], list[float]] = defaultdict(list)
        self.search_requests: dict[str, int] = defaultdict(int)
        self.search_durations: list[float] = []
        self.search_zero_results = 0
        self.ingest_total: dict[tuple[str, str], int] = defaultdict(int)
        self.case_assignment_total: dict[str, int] = defaultdict(int)
        self.doctor_failures: dict[str, int] = defaultdict(int)

    def record_http(self, method: str, route: str, status: int, duration: float) -> None:
        with self._lock:
            self.http_requests[(route, method, str(status))] += 1
            self.http_durations[(route, method)].append(duration)

    def record_search(self, path: str, duration: float, result_count: int) -> None:
        with self._lock:
            self.search_requests[path] += 1
            self.search_durations.append(duration)
            if result_count == 0:
                self.search_zero_results += 1

    def record_ingest(self, outcome: str, risk_level: str) -> None:
        with self._lock:
            self.ingest_total[(outcome, risk_level)] += 1

    def record_case_assignment(self, result: str) -> None:
        with self._lock:
            self.case_assignment_total[result] += 1

    def record_doctor_failure(self, failure_type: str) -> None:
        with self._lock:
            self.doctor_failures[failure_type] += 1

    def render_prometheus(self) -> str:
        lines = [
            "# HELP ma3_http_requests_total HTTP requests by route, method, and status.",
            "# TYPE ma3_http_requests_total counter",
        ]
        with self._lock:
            for (route, method, status), value in sorted(self.http_requests.items()):
                lines.append(f'ma3_http_requests_total{{route="{route}",method="{method}",status="{status}"}} {value}')
            lines.extend([
                "# HELP ma3_http_request_duration_seconds_sum HTTP request duration sum.",
                "# TYPE ma3_http_request_duration_seconds_sum counter",
            ])
            for (route, method), values in sorted(self.http_durations.items()):
                lines.append(f'ma3_http_request_duration_seconds_count{{route="{route}",method="{method}"}} {len(values)}')
                lines.append(f'ma3_http_request_duration_seconds_sum{{route="{route}",method="{method}"}} {sum(values):.6f}')
            lines.extend([
                "# HELP ma3_search_requests_total Search requests by candidate path.",
                "# TYPE ma3_search_requests_total counter",
            ])
            for path, value in sorted(self.search_requests.items()):
                lines.append(f'ma3_search_requests_total{{path="{path}"}} {value}')
            lines.append(f"ma3_search_zero_results_total {self.search_zero_results}")
            lines.append(f"ma3_search_duration_seconds_count {len(self.search_durations)}")
            lines.append(f"ma3_search_duration_seconds_sum {sum(self.search_durations):.6f}")
            for (outcome, risk), value in sorted(self.ingest_total.items()):
                lines.append(f'ma3_ingest_total{{outcome="{outcome}",risk_level="{risk}"}} {value}')
            for result, value in sorted(self.case_assignment_total.items()):
                lines.append(f'ma3_case_assignment_total{{result="{result}"}} {value}')
            for failure_type, value in sorted(self.doctor_failures.items()):
                lines.append(f'ma3_doctor_failures_total{{failure_type="{failure_type}"}} {value}')
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()


def now() -> float:
    return time.perf_counter()

