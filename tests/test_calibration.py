import unittest

from pydantic import ValidationError

from flowroute.calibration import CalibrationConfig


class CalibrationTests(unittest.TestCase):
    def test_all_risk_tiers_are_required(self):
        with self.assertRaises(ValidationError):
            CalibrationConfig(tiers={"low": {"route": 0.5, "margin": 0.1}})

    def test_thresholds_cannot_decrease_with_risk(self):
        with self.assertRaises(ValidationError):
            CalibrationConfig(
                tiers={
                    "low": {"route": 0.7, "margin": 0.1},
                    "medium": {"route": 0.6, "margin": 0.1},
                    "high": {"route": 0.8, "margin": 0.1},
                    "critical": {"route": 0.9, "margin": 0.1},
                }
            )


if __name__ == "__main__":
    unittest.main()
