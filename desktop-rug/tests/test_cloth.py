"""Headless physics tests for the cloth solver (numpy; uses the C helper when built)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    import numpy as np
    from desktop_rug import cloth as C
except Exception:          # pragma: no cover - numpy missing
    C = None


def run(cl, frames):
    for _ in range(frames):
        cl.step(1 / 60)


@unittest.skipIf(C is None, "numpy not installed")
class ClothTests(unittest.TestCase):
    def make(self):
        return C.Cloth(620, 390, 500, 400, 0)

    def test_grid_size(self):
        cl = self.make()
        self.assertTrue(2000 <= cl.nx * cl.ny <= 2800)
        self.assertAlmostEqual(cl.fold_amount(), 0.0, places=3)

    def test_flat_rug_sleeps_and_stays_flat(self):
        cl = self.make()
        run(cl, 400)
        self.assertTrue(cl.sleeping)
        self.assertLess(cl.fold_amount(), 2.0)
        cx, cy, ang = cl.fit_pose()
        self.assertAlmostEqual(cx, 500, delta=1)
        self.assertAlmostEqual(ang, 0, delta=0.5)

    def test_corner_fold_then_settle_without_stretch(self):
        cl = self.make()
        cl.start_grab(500 + 308, 400 + 193)       # bottom-right corner
        for i in range(1, 61):
            cl.drag_to(808 - 4.2 * i, 593 - 4.5 * i)
            cl.step(1 / 60)
        cl.end_grab()
        run(cl, 400)
        self.assertTrue(cl.sleeping)
        self.assertGreater(cl.fold_amount(), 150)
        # stiff: structural springs stay close to rest length
        d = np.linalg.norm(np.diff(cl.P, axis=1), axis=-1)
        self.assertLess(float(np.median(d)) / cl.dx, 1.05)
        self.assertTrue(np.isfinite(cl.P).all())
        self.assertGreaterEqual(float(cl.P[..., 2].min()), -0.01)   # never below the floor
        # flap rests on top of the rug (layer separation, no z-fighting)
        self.assertGreater(float(cl.P[-1, -1, 2]), C.THICK * 0.5)

    def test_unfold_animation_returns_flat(self):
        cl = self.make()
        pose = cl.fit_pose()
        cl.set_positions(cl.from_local(cl.corner_fold_local(), pose))
        self.assertGreater(cl.fold_amount(pose), 100)
        cl.animate_to(cl.flat_target(pose), duration=0.5)
        run(cl, 40)
        self.assertIsNone(cl.kinematic)
        self.assertLess(cl.fold_amount(pose), 1.0)

    def test_serialisation_roundtrip(self):
        cl = self.make()
        d = cl.to_dict()
        cl2 = C.Cloth(d["w"], d["h"], 0, 0, 0, d["nx"], d["ny"])
        cl2.set_positions(d["P"])
        self.assertLess(float(np.abs(cl2.P - cl.P).max()), 0.01)


if __name__ == "__main__":
    unittest.main()
