"""Synthetic unit tests only: they are not a rerun of Weber measurements."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from thermocouple_event import (
    EventOutcome, GradientSample, first_downward_event, one_sided_event_status,
    recorded_command_off_min, replay_first_event, trailing_gradients,
)


class EventOperatorTests(unittest.TestCase):
    def test_piecewise_cooling_first_event_interpolated(self):
        t = list(range(41))
        temp = [2.0 * min(x, 20) for x in t]
        event = replay_first_event(t, temp, action_min=40)
        self.assertEqual(event.status, "observed")
        self.assertAlmostEqual(event.first_crossing_min, 27.5, places=10)
        self.assertEqual(event.observation_horizon_min, 39)

    def test_irregular_timestamp_lag_interpolation(self):
        t = [0, 7, 14, 16, 20, 23, 30, 36]
        temp = [2.0 * min(x, 20) for x in t]
        gs = trailing_gradients(t, temp)
        self.assertAlmostEqual(gs[0].gradient_k_per_min, 2.0)
        self.assertAlmostEqual(gs[2].gradient_k_per_min, 1.6)
        outcome = first_downward_event(gs)
        self.assertAlmostEqual(outcome.first_crossing_min, 27.5, places=10)

    def test_initial_below_does_not_arm(self):
        t = list(range(30))
        out = replay_first_event(t, [20.0] * len(t))
        self.assertEqual(out.status, "right_censored")
        self.assertIsNone(out.first_crossing_min)

    def test_strict_preaction_censoring(self):
        t = list(range(41))
        temp = [2.0 * min(x, 20) for x in t]
        out = replay_first_event(t, temp, action_min=27)
        self.assertEqual(out.status, "right_censored")
        self.assertEqual(out.observation_horizon_min, 26)
        self.assertEqual(one_sided_event_status(out, 25.0), "deadline_missed_censored")
        self.assertEqual(one_sided_event_status(out, 29.0), "unresolved_censored")

    def test_no_gradient_window(self):
        out = replay_first_event([0, 3, 5], [0, 5, 8])
        self.assertEqual(out.gradient_count, 0)
        self.assertEqual(out.status, "right_censored")

    def test_crossing_exact_threshold_endpoint(self):
        gs = [GradientSample(15, 1.0), GradientSample(17, 0.8)]
        out = first_downward_event(gs, 1.0, 17)
        self.assertAlmostEqual(out.first_crossing_min, 15.0)

    def test_recovery_after_below_threshold_without_prior_above(self):
        gs = [GradientSample(15, 0.4), GradientSample(16, 0.5), GradientSample(17, 1.3), GradientSample(18, 0.7)]
        self.assertAlmostEqual(first_downward_event(gs).first_crossing_min, 17.5)

    def test_detect_command_after_longest_on_segment(self):
        t = list(range(12))
        heater = [4, 7, 7, 4, 4, 7, 7, 7, 7, 4, 4, 4]
        self.assertEqual(recorded_command_off_min(t, heater), 9)

    def test_command_without_off_is_not_observed(self):
        self.assertIsNone(recorded_command_off_min([0, 1, 2], [7, 7, 7]))

    def test_validation_rejects_bad_time(self):
        with self.assertRaises(ValueError):
            trailing_gradients([0, 1, 1], [5, 6, 7])
        with self.assertRaises(ValueError):
            trailing_gradients([0, 1], [0, 1], window_min=0)

    def test_one_sided_statuses(self):
        event = EventOutcome("observed", 19.0, 25, 11)
        self.assertEqual(one_sided_event_status(event, 20), "within_one_sided_window")
        self.assertEqual(one_sided_event_status(event, 25), "too_early")
        self.assertEqual(one_sided_event_status(event, 18), "after_source_deadline")

    def test_no_missing_values_accepted(self):
        with self.assertRaises(ValueError):
            replay_first_event([0, 1], [1.0, float("nan")])


if __name__ == "__main__":
    unittest.main()
