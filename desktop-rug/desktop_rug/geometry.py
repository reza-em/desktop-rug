"""Pure-python fold / transform math (no Qt), unit-testable.

Rug-local coordinates: origin at rug centre, x right, y down, unrotated.
The rug occupies [-w/2, w/2] x [-h/2, h/2]. The foldable corner is the
bottom-right corner C = (w/2, h/2). Folding moves C to point P; the crease
is the perpendicular bisector of C-P and the part of the rug on C's side of
the crease is mirrored over it (showing the rug's underside).
"""
import math

Vec = tuple


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def mul(a, s):
    return (a[0] * s, a[1] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def length(a):
    return math.hypot(a[0], a[1])


def rect_poly(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def corner(w, h):
    return (w / 2, h / 2)


def fold_line(w, h, p):
    """Return (M, n) - a point on the crease and unit normal pointing to C.
    None if P == C (no fold)."""
    c = corner(w, h)
    d = sub(c, p)
    L = length(d)
    if L < 1e-6:
        return None
    n = (d[0] / L, d[1] / L)
    m = mul(add(c, p), 0.5)
    return m, n


def clip_halfplane(poly, m, n, keep_positive):
    """Sutherland-Hodgman clip of polygon against half-plane (X-M).n >= 0
    (keep_positive) or <= 0."""
    def side(pt):
        s = dot(sub(pt, m), n)
        return s if keep_positive else -s

    out = []
    if not poly:
        return out
    prev = poly[-1]
    sp = side(prev)
    for cur in poly:
        sc = side(cur)
        if sc >= 0:
            if sp < 0:
                t = sp / (sp - sc)
                out.append(add(prev, mul(sub(cur, prev), t)))
            out.append(cur)
        elif sp >= 0:
            t = sp / (sp - sc)
            out.append(add(prev, mul(sub(cur, prev), t)))
        prev, sp = cur, sc
    return out


def reflect(pt, m, n):
    s = dot(sub(pt, m), n)
    return sub(pt, mul(n, 2 * s))


def reflection_matrix(m, n):
    """Affine reflection over the crease as (a, b, c, d, tx, ty) so that
    x' = a*x + c*y + tx ; y' = b*x + d*y + ty  (QTransform m11,m12,m21,m22,dx,dy)."""
    nx, ny = n
    a = 1 - 2 * nx * nx
    b = -2 * nx * ny
    d = 1 - 2 * ny * ny
    k = 2 * dot(m, n)
    return (a, b, b, d, k * nx, k * ny)


def fold_polys(w, h, p):
    """Return (base_poly, flap_src_poly, flap_dst_poly, crease_segment).
    flap_src is the region of the rug that is lifted (in unfolded coords),
    flap_dst is where it lands after mirroring. crease = (p0, p1) or None."""
    rect = rect_poly(w, h)
    fl = fold_line(w, h, p)
    if fl is None:
        return rect, [], [], None
    m, n = fl
    base = clip_halfplane(rect, m, n, keep_positive=False)
    src = clip_halfplane(rect, m, n, keep_positive=True)
    dst = [reflect(q, m, n) for q in src]
    # crease = points on the line shared by base and src
    pts = [q for q in src if abs(dot(sub(q, m), n)) < 1e-6]
    crease = (pts[0], pts[-1]) if len(pts) >= 2 else None
    if crease and len(pts) > 2:
        best = max(((a, b) for a in pts for b in pts), key=lambda ab: length(sub(ab[0], ab[1])))
        crease = best
    return base, src, dst, crease


def clamp_fold_point(w, h, p, margin=0.0):
    """Keep the fold point inside the rug (so the flap stays on the rug,
    like the reference demo) and away from the far corner."""
    x = min(max(p[0], -w / 2 + margin), w / 2)
    y = min(max(p[1], -h / 2 + margin), h / 2)
    return (x, y)


def to_global(pt, center, angle_deg):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    return (center[0] + pt[0] * ca - pt[1] * sa, center[1] + pt[0] * sa + pt[1] * ca)


def to_local(pt, center, angle_deg):
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    dx, dy = pt[0] - center[0], pt[1] - center[1]
    return (dx * ca + dy * sa, -dx * sa + dy * ca)


def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
