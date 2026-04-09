from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class MetricsStore:
    """Track process-level request and model metrics."""

    start_time: float = field(default_factory=time.time)
    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    requests_rejected: int = 0
    total_processing_ms: float = 0.0
    gemini_calls_total: int = 0
    gemini_calls_failed: int = 0
    gemini_total_ms: float = 0.0
    rate_limit_hits: int = 0

    def avg_processing_ms(self) -> float:
        """Return average request duration in milliseconds."""
        if self.requests_total == 0:
            return 0.0
        return round(self.total_processing_ms / self.requests_total, 2)

    def uptime_seconds(self) -> int:
        """Return process uptime in seconds."""
        return int(time.time() - self.start_time)

    def to_dict(self) -> dict:
        """Return metrics as a serializable dictionary."""
        return {
            'uptime_seconds': self.uptime_seconds(),
            'requests_total': self.requests_total,
            'requests_success': self.requests_success,
            'requests_failed': self.requests_failed,
            'requests_rejected': self.requests_rejected,
            'avg_processing_ms': self.avg_processing_ms(),
            'gemini_calls_total': self.gemini_calls_total,
            'gemini_calls_failed': self.gemini_calls_failed,
            'gemini_avg_ms': round(self.gemini_total_ms / max(self.gemini_calls_total, 1), 2),
            'rate_limit_hits': self.rate_limit_hits,
        }


metrics = MetricsStore()
