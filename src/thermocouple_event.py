"""Minimal independent replay of the DGIG source-compatible first-event operator.

This is *not* an exact copy of the unavailable historical supervisory
controller code or the paper's full fit/reproduction pipeline. All time values
are elapsed MINUTES, and all gradients are degrees Celsius per minute.

No smoothing, resampling, imputation, or future samples are used. In a replay
with a recorded off-command, pass the first off-command time as `action_min`
to exclude that sample and everything after it.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite
from typing import Sequence

WINDOW_MIN = 15.0
THRESHOLD_K_PER_MIN = 1.0
HEATER_ON_MA = 4.5


@dataclass(frozen=True)
class GradientSample:
    time_min: float
    gradient_k_per_min: float


@dataclass(frozen=True)
class EventOutcome:
    status: str
    first_crossing_min: float | None
    observation_horizon_min: float | None
    gradient_count: int


def _validate_trace(times_min: Sequence[float], values: Sequence[float]) -> None:
    if not times_min or len(times_min) != len(values):
        raise ValueError("time and value arrays must be nonempty and equally sized")
    for i, (t, v) in enumerate(zip(times_min, values)):
        if not (isfinite(t) and isfinite(v)):
            raise ValueError("nonfinite time or value")
        if i > 0 and not t > times_min[i - 1]:
            raise ValueError("time must be strictly increasing")


def recorded_command_off_min(
    times_min: Sequence[float], heater_ma: Sequence[float],
    on_threshold_ma: float = HEATER_ON_MA,
) -> float | None:
    """First off sample after longest observed contiguous heater-on segment.

    This segment selection is retrospective. An on segment that reaches the
    final sample has no subsequent recorded off command and is ineligible.
    Ties are resolved in favour of the earliest segment.
    """
    _validate_trace(times_min, heater_ma)
    if not isfinite(on_threshold_ma):
        raise ValueError("invalid heater threshold")
    n = len(times_min)
    eligible: list[tuple[float, int]] = []
    i = 0
    while i < n:
        if heater_ma[i] <= on_threshold_ma:
            i += 1
            continue
        start = i
        while i < n and heater_ma[i] > on_threshold_ma:
            i += 1
        if i < n:
            eligible.append((times_min[i - 1] - times_min[start], i))
    if not eligible:
        return None
    # Earliest off-sample breaks duration ties.
    duration, off_idx = max(eligible, key=lambda z: (z[0], -z[1]))
    return times_min[off_idx]


def trailing_gradients(
    times_min: Sequence[float], temperatures_c: Sequence[float],
    window_min: float = WINDOW_MIN,
    action_min: float | None = None,
) -> list[GradientSample]:
    """Finite-interval gradient using linear interpolation of the lagged sample.

    The input is assumed to begin at the reconstructed heater-on sample.
    `action_min` gives the first recorded off sample; only times strictly
    before it are eligible. There is no extrapolation beyond supplied times.
    """
    _validate_trace(times_min, temperatures_c)
    if not isfinite(window_min) or window_min <= 0:
        raise ValueError("window_min must be finite and positive")
    if action_min is not None and not isfinite(action_min):
        raise ValueError("action_min must be finite")
    output: list[GradientSample] = []
    start_time = times_min[0]
    for i, now in enumerate(times_min):
        if action_min is not None and now >= action_min:
            break
        lag = now - window_min
        if lag < start_time:
            continue
        j = bisect_right(times_min, lag, 0, i + 1) - 1
        if j < 0:
            continue
        if times_min[j] == lag:
            earlier = temperatures_c[j]
        else:
            if j + 1 > i:
                raise ValueError("interpolation would require future observation")
            alpha = (lag - times_min[j]) / (times_min[j + 1] - times_min[j])
            earlier = temperatures_c[j] + alpha * (temperatures_c[j + 1] - temperatures_c[j])
        output.append(GradientSample(now, (temperatures_c[i] - earlier) / window_min))
    return output


def first_downward_event(
    gradients: Sequence[GradientSample], threshold: float = THRESHOLD_K_PER_MIN,
    observation_horizon_min: float | None = None,
) -> EventOutcome:
    """First armed g_prev >= threshold and g_next < threshold crossing.

    A series that starts below the threshold without an earlier at/above
    value is not armed and is right-censored; absent events are never imputed.
    """
    if not isfinite(threshold):
        raise ValueError("threshold must be finite")
    if observation_horizon_min is not None and not isfinite(observation_horizon_min):
        raise ValueError("invalid observation horizon")
    prev: GradientSample | None = None
    for point in gradients:
        if not (isfinite(point.time_min) and isfinite(point.gradient_k_per_min)):
            raise ValueError("invalid gradient sample")
        if prev is not None:
            if point.time_min <= prev.time_min:
                raise ValueError("gradients must have increasing time")
            if prev.gradient_k_per_min >= threshold > point.gradient_k_per_min:
                g0, g1 = prev.gradient_k_per_min, point.gradient_k_per_min
                frac = (g0 - threshold) / (g0 - g1)
                event_time = prev.time_min + frac * (point.time_min - prev.time_min)
                return EventOutcome("observed", event_time, observation_horizon_min, len(gradients))
        prev = point
    return EventOutcome("right_censored", None, observation_horizon_min, len(gradients))


def replay_first_event(
    times_min: Sequence[float], temperatures_c: Sequence[float],
    *, action_min: float | None = None,
    window_min: float = WINDOW_MIN, threshold: float = THRESHOLD_K_PER_MIN,
) -> EventOutcome:
    """Return the source-compatible first event or right-censoring record."""
    gradients = trailing_gradients(times_min, temperatures_c, window_min, action_min)
    eligible = [t for t in times_min if action_min is None or t < action_min]
    horizon = eligible[-1] if eligible else None
    return first_downward_event(gradients, threshold, horizon)


def one_sided_event_status(
    event: EventOutcome, source_event_min: float,
    early_allowance_min: float = 5.0,
) -> str:
    """Status for the descriptive [source-allowance, source] first-event window.

    This window is not an engineering safety tolerance. A censored search
    whose horizon reaches the source event has missed the one-sided deadline;
    an earlier censoring horizon cannot resolve the outcome.
    """
    if not isfinite(source_event_min) or early_allowance_min < 0 or not isfinite(early_allowance_min):
        raise ValueError("invalid source event or early allowance")
    if event.status == "observed":
        t = event.first_crossing_min
        if t is None:
            raise ValueError("observed status requires event time")
        if source_event_min - early_allowance_min <= t <= source_event_min:
            return "within_one_sided_window"
        return "too_early" if t < source_event_min - early_allowance_min else "after_source_deadline"
    if event.status != "right_censored":
        raise ValueError("unknown event status")
    h = event.observation_horizon_min
    return "deadline_missed_censored" if h is not None and h >= source_event_min else "unresolved_censored"
