"""Synthetic clock-boundary and frozen output checks, no original measurement data."""
import csv, unittest
from pathlib import Path
from lead_certificate import strict_preaction_indices

ROOT = Path(__file__).resolve().parent
class TestStrictPreaction(unittest.TestCase):
    def test_excludes_logged_command_time(self):
        self.assertEqual(strict_preaction_indices([0.0, 1.0, 2.0], 2.0), (0, 1))
    def test_no_preaction_sample_if_command_is_first(self):
        self.assertEqual(strict_preaction_indices([0.0, 1.0], 0.0), ())
    def test_nonmonotone_rejected(self):
        with self.assertRaises(ValueError):
            strict_preaction_indices([0.0, 1.0, 0.9], 2.0)
    def test_full_grid_scope_counts(self):
        with (ROOT/'summary_grid.csv').open(newline='') as f: items=list(csv.DictReader(f))
        self.assertEqual(len(items), 50)
        sel=lambda h,d: next(r for r in items if float(r['halfwidth_K_min'])==h and float(r['delta_raw_K'])==d)
        for d,passes,lower in [(1.0,24,16.11),(1.5,24,11.56),(1.6,23,None)]:
            v=sel(.01,d)
            self.assertEqual(int(v['passes_24']), passes)
            if lower is not None:
                self.assertGreater(float(v['full_24_min_guaranteed_lead_min']),lower)
            else:
                self.assertFalse(v['full_24_min_guaranteed_lead_min'])
    def test_linear_joint_radius_relation(self):
        with (ROOT/'joint_radii_24.csv').open(newline='') as f: vals=list(csv.DictReader(f))
        self.assertEqual(len(vals),120)
        ref={(r['run'],r['sensor']):float(r['certificate_error_radius_K']) for r in vals if float(r['halfwidth_K_min'])==0}
        for r in vals:
            target=max(0,ref[r['run'],r['sensor']]-7.5*float(r['halfwidth_K_min']))
            self.assertAlmostEqual(float(r['certificate_error_radius_K']),target,places=8)

if __name__ == '__main__': unittest.main()
