import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from desktop_rug import geometry as G


def area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


class FoldTests(unittest.TestCase):
    def test_flat(self):
        base, src, dst, crease = G.fold_polys(600, 400, (300, 200))
        self.assertEqual(len(base), 4)
        self.assertEqual(src, [])

    def test_area_conserved(self):
        w, h = 600, 400
        for p in [(100, 50), (0, 0), (250, 190), (-200, -150), (290, -180)]:
            base, src, dst, crease = G.fold_polys(w, h, p)
            self.assertAlmostEqual(area(base) + area(src), w * h, places=3)
            self.assertAlmostEqual(area(src), area(dst), places=3)
            self.assertIsNotNone(crease)

    def test_corner_lands_on_p(self):
        w, h, p = 600, 400, (40, -30)
        m, n = G.fold_line(w, h, p)
        c = G.reflect(G.corner(w, h), m, n)
        self.assertAlmostEqual(c[0], p[0], places=6)
        self.assertAlmostEqual(c[1], p[1], places=6)

    def test_reflection_matrix_matches(self):
        m, n = G.fold_line(600, 400, (10, 20))
        a, b, c, d, tx, ty = G.reflection_matrix(m, n)
        for q in [(0, 0), (100, -50), (300, 200)]:
            r = G.reflect(q, m, n)
            self.assertAlmostEqual(a * q[0] + c * q[1] + tx, r[0], places=6)
            self.assertAlmostEqual(b * q[0] + d * q[1] + ty, r[1], places=6)

    def test_transforms_roundtrip(self):
        for ang in (-37, 0, 12.5, 90, 181):
            g = G.to_global((123, -45), (500, 400), ang)
            l = G.to_local(g, (500, 400), ang)
            self.assertAlmostEqual(l[0], 123, places=6)
            self.assertAlmostEqual(l[1], -45, places=6)

    def test_point_in_poly(self):
        poly = G.rect_poly(10, 10)
        self.assertTrue(G.point_in_poly((0, 0), poly))
        self.assertFalse(G.point_in_poly((6, 0), poly))


if __name__ == "__main__":
    unittest.main()
