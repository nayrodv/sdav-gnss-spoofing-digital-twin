from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import statistics


@dataclass
class DetectorConfig:
    baseline_samples: int = 200
    sigma_multiplier: float = 4.0
    minimum_threshold_m: float = 5.0
    persistence_samples: int = 8
    recovery_samples: int = 20
    maximum_message_age_s: float = 0.5


@dataclass
class DetectorOutput:
    residual_m: float
    threshold_m: float
    persistent_count: int
    suspected: bool
    recovered: bool


class ResidualSpoofingDetector:
    """Simple research prototype for physical-vs-predicted position residuals.

    It is intentionally conservative and is not flight-certified. The detector
    establishes a benign residual baseline, applies a minimum threshold, and
    requires temporal persistence before raising an event.
    """

    def __init__(self, config: DetectorConfig | None = None):
        self.config = config or DetectorConfig()
        self.baseline: list[float] = []
        self.window: deque[bool] = deque(maxlen=self.config.persistence_samples)
        self.recovery_window: deque[bool] = deque(maxlen=self.config.recovery_samples)
        self.active = False

    def threshold(self) -> float:
        if len(self.baseline) < 10:
            return self.config.minimum_threshold_m
        mu = statistics.fmean(self.baseline)
        sigma = statistics.pstdev(self.baseline)
        return max(self.config.minimum_threshold_m, mu + self.config.sigma_multiplier * sigma)

    def update(self, gps_n: float, gps_e: float, pred_n: float, pred_e: float, message_age_s: float = 0.0) -> DetectorOutput:
        residual = math.hypot(gps_n - pred_n, gps_e - pred_e)
        if len(self.baseline) < self.config.baseline_samples and message_age_s <= self.config.maximum_message_age_s:
            self.baseline.append(residual)
        threshold = self.threshold()
        exceed = residual > threshold and message_age_s <= self.config.maximum_message_age_s
        self.window.append(exceed)
        persistent = sum(self.window)
        if len(self.window) == self.window.maxlen and persistent == self.window.maxlen:
            self.active = True
        self.recovery_window.append(residual <= 0.75 * threshold)
        recovered = self.active and len(self.recovery_window) == self.recovery_window.maxlen and all(self.recovery_window)
        if recovered:
            self.active = False
            self.window.clear()
        return DetectorOutput(residual, threshold, persistent, self.active, recovered)
