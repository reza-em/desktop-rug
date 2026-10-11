"""Real-time rug cloth simulation (position based dynamics, numpy-vectorised).

World space = global desktop pixels: x right, y down, z = height above the
desktop "floor" (towards the viewer). The rug is an NY x NX particle grid with
  * structural constraints (red/black Gauss-Seidel, exact),
  * shear (diagonal) and bending (distance-2) constraints (Jacobi, softer),
  * gravity, floor collision with static/kinetic friction,
  * long-range tethers from the grabbed particle (no stretching, the rug slides
    along when pulled further than it can reach),
  * layer separation (binned self-collision) so folded layers lie on top of
    each other at rug thickness instead of z-fighting,
  * fringe strands (ریشه) on both short ends, simulated as little chains.
"""
import ctypes
import math
import os
import sys
import numpy as np


def _load_native():
    if os.environ.get("DESKTOP_RUG_NO_NATIVE"):
        return None
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "native")
    name = "clothsim.dll" if sys.platform.startswith("win") else "libclothsim.so"
    try:
        lib = ctypes.CDLL(os.path.join(here, name))
        dp = ctypes.POINTER(ctypes.c_double)
        lib.cloth_constraints.argtypes = [dp, dp, ctypes.c_int, ctypes.c_int, ctypes.c_double,
                                          ctypes.c_double, ctypes.c_int, ctypes.c_double,
                                          ctypes.c_double, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                          ctypes.c_int, ctypes.c_int, dp, ctypes.c_int, dp]
        lib.cloth_constraints.restype = None
        return lib
    except OSError:
        return None


NATIVE = _load_native()

GRAVITY = 2600.0        # px / s^2
THICK = 5.0             # rug thickness (layer separation) px


def rot2(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


class Cloth:
    def __init__(self, w, h, cx, cy, angle_deg, nx=None, ny=None):
        self.w, self.h = float(w), float(h)
        if nx is None:
            # ~2400 particles, square-ish cells
            cells = 2400
            ar = self.w / self.h
            ny = max(12, int(round(math.sqrt(cells / ar))))
            nx = max(12, int(round(cells / ny)))
        self.nx, self.ny = nx, ny
        self.dx = self.w / (nx - 1)
        self.dy = self.h / (ny - 1)
        u = np.linspace(-self.w / 2, self.w / 2, nx)
        v = np.linspace(-self.h / 2, self.h / 2, ny)
        U, V = np.meshgrid(u, v)
        self.rest = np.stack([U, V], -1)                    # (ny, nx, 2) local rest coords
        self.uv = np.stack([(U + self.w / 2) / self.w, (V + self.h / 2) / self.h], -1)
        self.W = np.ones((ny, nx))                          # inverse mass (0 = pinned)
        self.iy, self.ix = np.mgrid[0:ny, 0:nx]
        self.grab = None
        self.kinematic = None                               # animation in progress
        self.bumps = None                                   # (K,2) icon positions under the rug
        self.contact = np.zeros((ny, nx), bool)
        self.set_flat(cx, cy, angle_deg)
        self._init_fringe()
        self.sleep_frames = 0
        self.sleeping = False

    # ------------------------------------------------------------------ poses
    def pose_points(self, cx, cy, angle_deg, local=None):
        local = self.rest if local is None else local
        R = rot2(math.radians(angle_deg))
        xy = local[..., :2] @ R.T + np.array([cx, cy])
        return xy

    def set_flat(self, cx, cy, angle_deg):
        xy = self.pose_points(cx, cy, angle_deg)
        self.P = np.concatenate([xy, np.zeros(xy.shape[:-1] + (1,))], -1)
        self.prev = self.P.copy()
        self.cx, self.cy, self.angle = float(cx), float(cy), float(angle_deg)
        self.wake()

    def set_positions(self, P):
        P = np.asarray(P, float).reshape(self.ny, self.nx, 3)
        self.P = P.copy()
        self.prev = P.copy()
        self.wake()

    def fit_pose(self):
        """Best rigid 2D pose of the bottom (face-up, on-floor) layer -> (cx, cy, angle)."""
        n = self.normals()
        m = (n[..., 2] > 0.3) & (self.P[..., 2] < THICK * 0.7)
        if m.sum() < 0.15 * m.size:
            m = np.ones_like(m)
        r = self.rest[m]
        p = self.P[m][:, :2]
        cr, cp = r.mean(0), p.mean(0)
        r0, p0 = r - cr, p - cp
        num = (r0[:, 0] * p0[:, 1] - r0[:, 1] * p0[:, 0]).sum()
        den = (r0[:, 0] * p0[:, 0] + r0[:, 1] * p0[:, 1]).sum()
        a = math.atan2(num, den)
        t = cp - rot2(a) @ cr
        return float(t[0]), float(t[1]), math.degrees(a)

    def to_local(self, P, pose):
        cx, cy, ang = pose
        R = rot2(math.radians(ang))
        xy = (P[..., :2] - np.array([cx, cy])) @ R
        return np.concatenate([xy, P[..., 2:3]], -1)

    def from_local(self, L, pose):
        cx, cy, ang = pose
        xy = self.pose_points(cx, cy, ang, L)
        return np.concatenate([xy, L[..., 2:3]], -1)

    def flat_target(self, pose):
        xy = self.pose_points(*pose)
        return np.concatenate([xy, np.zeros(xy.shape[:-1] + (1,))], -1)

    def fold_amount(self, pose=None):
        """Max displacement (px) from the flat configuration."""
        pose = pose or self.fit_pose()
        T = self.flat_target(pose)
        dxy = np.linalg.norm(self.P[..., :2] - T[..., :2], axis=-1)
        floor = self._floor()
        z = self.P[..., 2] - (0.0 if floor is None else floor)   # bumps over icons are not folds
        dz = np.maximum(z - 1.0, 0.0)
        return float(np.sqrt(dxy ** 2 + dz ** 2).max())

    # ------------------------------------------------------------------ rigid edits
    def translate(self, dx, dy):
        off = np.array([dx, dy, 0.0])
        self.P += off
        self.prev += off
        self.fr_P += off
        self.fr_prev += off
        self.wake()

    def rotate(self, dang_deg, center=None):
        c = np.array(center if center is not None else self.P[..., :2].reshape(-1, 2).mean(0))
        R = rot2(math.radians(dang_deg))
        for arr in (self.P, self.prev, self.fr_P, self.fr_prev):
            arr[..., :2] = (arr[..., :2] - c) @ R.T + c
        self.wake()

    # ------------------------------------------------------------------ geometry
    def normals(self):
        P = self.P
        du = np.zeros_like(P)
        dv = np.zeros_like(P)
        du[:, 1:-1] = P[:, 2:] - P[:, :-2]
        du[:, 0] = P[:, 1] - P[:, 0]
        du[:, -1] = P[:, -1] - P[:, -2]
        dv[1:-1] = P[2:] - P[:-2]
        dv[0] = P[1] - P[0]
        dv[-1] = P[-1] - P[-2]
        n = np.cross(du, dv)
        n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
        return n

    def bbox(self):
        xy = self.P[..., :2].reshape(-1, 2)
        z = self.P[..., 2].max()
        fr = self.fr_P[..., :2].reshape(-1, 2)
        allp = np.concatenate([xy, fr])
        return allp.min(0), allp.max(0), float(z)

    # ------------------------------------------------------------------ fringe
    def _init_fringe(self):
        rng = np.random.default_rng(11)
        ny = self.ny
        S = (ny - 1) * 2 + 1                       # strands per end
        self.fr_t = np.linspace(0, ny - 1, S)      # fractional row of each root
        self.fr_K = 5                              # nodes per strand incl. root
        base_len = max(10.0, min(self.w, self.h) * 0.055)
        self.fr_len = base_len * (0.8 + 0.35 * rng.random((2, S)))
        self.fr_shade = 0.82 + 0.25 * rng.random((2, S))
        self.fr_P = np.zeros((2, S, self.fr_K, 3))
        self._fringe_rest_layout()
        self.fr_prev = self.fr_P.copy()

    def _fringe_roots(self):
        """Root position + outward direction for each strand (from cloth edge)."""
        t = self.fr_t
        i0 = np.floor(t).astype(int).clip(0, self.ny - 2)
        f = (t - i0)[:, None]
        out = []
        for e, col, nb in ((0, 0, 1), (1, self.nx - 1, self.nx - 2)):
            p = self.P[i0, col] * (1 - f) + self.P[i0 + 1, col] * f
            q = self.P[i0, nb] * (1 - f) + self.P[i0 + 1, nb] * f
            d = p - q
            d /= np.linalg.norm(d, axis=-1, keepdims=True) + 1e-9
            out.append((p, d))
        return out

    def _fringe_rest_layout(self):
        for e, (root, d) in enumerate(self._fringe_roots()):
            seg = (self.fr_len[e] / (self.fr_K - 1))[:, None]
            for k in range(self.fr_K):
                self.fr_P[e, :, k] = root + d * seg * k

    def _step_fringe(self, dt):
        roots = self._fringe_roots()
        v = (self.fr_P - self.fr_prev) * 0.96
        self.fr_prev = self.fr_P.copy()
        self.fr_P = self.fr_P + v
        self.fr_P[..., 2] -= GRAVITY * dt * dt
        for e, (root, d) in enumerate(roots):
            self.fr_P[e, :, 0] = root
            self.fr_prev[e, :, 0] = root
        seg = (self.fr_len / (self.fr_K - 1))[..., None]
        for _ in range(3):
            for k in range(1, self.fr_K):
                a = self.fr_P[:, :, k - 1]
                b = self.fr_P[:, :, k]
                dd = b - a
                L = np.linalg.norm(dd, axis=-1, keepdims=True) + 1e-9
                corr = dd * (1 - seg / L)
                if k == 1:
                    self.fr_P[:, :, k] -= corr
                else:
                    self.fr_P[:, :, k - 1] += corr * 0.5
                    self.fr_P[:, :, k] -= corr * 0.5
            # mild stiffness: keep strands continuing the rug's direction near the root
            for e, (root, d) in enumerate(roots):
                want = root + d * seg[e] * 1.0
                self.fr_P[e, :, 1] += (want - self.fr_P[e, :, 1]) * 0.25
        # floor + friction
        z = self.fr_P[..., 2]
        under = z < 0.6
        z[under] = 0.6
        vv = self.fr_P - self.fr_prev
        vv[under, 0] *= 0.6
        vv[under, 1] *= 0.6
        vv[under, 2] = 0
        self.fr_prev = self.fr_P - vv

    # ------------------------------------------------------------------ interaction
    def pick(self, x, y):
        """Topmost particle near (x, y) -> (iy, ix) or None."""
        d2 = (self.P[..., 0] - x) ** 2 + (self.P[..., 1] - y) ** 2
        r = 1.6 * max(self.dx, self.dy)
        near = d2 < r * r
        if not near.any():
            i = int(np.argmin(d2))
            return divmod(i, self.nx)
        score = np.where(near, self.P[..., 2] * 10.0 - np.sqrt(d2) * 0.2, -1e9)
        i = int(np.argmax(score))
        return divmod(i, self.nx)

    def start_grab(self, x, y):
        self.kinematic = None
        iy, ix = self.pick(x, y)
        g = self.P[iy, ix]
        # rigid 3x3 patch around the grabbed particle (avoids a spike)
        ys = slice(max(0, iy - 1), min(self.ny, iy + 2))
        xs = slice(max(0, ix - 1), min(self.nx, ix + 2))
        # grabbing an edge (away from the corners) holds the whole edge like a
        # hand-held bar, so the rug folds over evenly instead of bunching
        ny, nx = self.ny, self.nx
        cy0, cx0 = 0.2 * ny, 0.2 * nx
        if ix <= 1 and cy0 < iy < ny - 1 - cy0:
            ys, xs = slice(0, ny), slice(0, 2)
        elif ix >= nx - 2 and cy0 < iy < ny - 1 - cy0:
            ys, xs = slice(0, ny), slice(nx - 2, nx)
        elif iy <= 1 and cx0 < ix < nx - 1 - cx0:
            ys, xs = slice(0, 2), slice(0, nx)
        elif iy >= ny - 2 and cx0 < ix < nx - 1 - cx0:
            ys, xs = slice(ny - 2, ny), slice(0, nx)
        patch_off = self.P[ys, xs] - g
        patch_off[..., 2] = 0.0
        self.grab = dict(iy=iy, ix=ix, ys=ys, xs=xs, off=patch_off,
                         grab_off=np.array([g[0] - x, g[1] - y]),
                         start=np.array([x, y]), target=g.copy(), lift=g[2])
        self.W[:] = 1.0
        self.W[ys, xs] = 0.0
        r = self.rest[iy, ix]
        self.tether = np.linalg.norm(self.rest - r, axis=-1) * 1.01
        self.wake()
        return iy, ix

    def drag_to(self, x, y):
        if not self.grab:
            return
        g = self.grab
        dist = float(np.linalg.norm(np.array([x, y]) - g["start"]))
        lift = min(95.0, 18.0 + dist * 0.45)
        g["target"] = np.array([x + g["grab_off"][0], y + g["grab_off"][1], lift])
        self.wake()

    def end_grab(self):
        self.grab = None
        self.W[:] = 1.0
        self.wake()

    # ------------------------------------------------------------------ animation
    def animate_to(self, target, duration=0.75, arc=0.38):
        """Kinematic, smooth transition (used for unfold / refold): every particle
        travels to its target along an arc whose height grows with its travel
        distance, so the flap swings over like a real rug being flipped back."""
        self.grab = None
        self.W[:] = 1.0
        start = self.P.copy()
        dist = np.linalg.norm(target[..., :2] - start[..., :2], axis=-1)
        self.kinematic = dict(start=start, target=np.asarray(target, float), t=0.0,
                              dur=duration, h=dist * arc)
        self.wake()

    def _step_kinematic(self, dt):
        k = self.kinematic
        k["t"] += dt
        s = min(1.0, k["t"] / k["dur"])
        e = s * s * (3 - 2 * s)                    # smoothstep
        P = k["start"] * (1 - e) + k["target"] * e
        P[..., 2] += np.sin(math.pi * e) * k["h"]
        self.prev = self.P
        self.P = P
        if s >= 1.0:
            self.P = k["target"].copy()
            self.prev = self.P.copy()
            self.kinematic = None

    # ------------------------------------------------------------------ physics
    def wake(self):
        self.sleeping = False
        self.sleep_frames = 0
        self.since_release = 0

    def _solve_pair(self, A, B, WA, WB, rest, k, compress_only=False):
        d = B - A
        L = np.sqrt((d * d).sum(-1)) + 1e-9
        diff = (L - rest) / L
        if compress_only:
            diff = np.minimum(diff, 0.0)
        wsum = WA + WB + 1e-9
        c = d * (diff * k / wsum)[..., None]
        A += c * WA[..., None]
        B -= c * WB[..., None]

    K_SHEAR = 0.45
    SEP_BIN = 1.6
    SEP_NEAR = 2
    SEP_OFFSETS = (0.0, 0.5)
    K_BEND = 0.16

    def _constraints(self, iters):
        if NATIVE is not None:
            return self._constraints_native(iters)
        P, W = self.P, self.W
        nx, ny = self.nx, self.ny
        dx, dy = self.dx, self.dy
        dd = math.hypot(dx, dy)
        for _ in range(iters):
            for s in (0, 1):   # structural, red/black => exact Gauss-Seidel
                self._solve_pair(P[:, s:nx - 1:2], P[:, s + 1:nx:2], W[:, s:nx - 1:2], W[:, s + 1:nx:2], dx, 1.0)
            for s in (0, 1):
                self._solve_pair(P[s:ny - 1:2], P[s + 1:ny:2], W[s:ny - 1:2], W[s + 1:ny:2], dy, 1.0)
            self._solve_pair(P[:-1, :-1], P[1:, 1:], W[:-1, :-1], W[1:, 1:], dd, 0.45)
            self._solve_pair(P[:-1, 1:], P[1:, :-1], W[:-1, 1:], W[1:, :-1], dd, 0.45)
            # bending: thick, stiff rug (resists compression of distance-2 pairs)
            self._solve_pair(P[:, :-2], P[:, 2:], W[:, :-2], W[:, 2:], 2 * dx, 0.16)
            self._solve_pair(P[:-2], P[2:], W[:-2], W[2:], 2 * dy, 0.16)
            if self.grab:
                g = self.grab
                tgt = g["target"]
                P[g["ys"], g["xs"]] = tgt + g["off"] * np.array([1, 1, 0.3])
                # long-range tethers: nothing may be further from the grab than its rest distance
                gp = P[g["iy"], g["ix"]]
                d = P - gp
                L = np.sqrt((d * d).sum(-1)) + 1e-9
                over = L > self.tether
                if over.any():
                    f = np.where(over, self.tether / L, 1.0)[..., None]
                    P[:] = np.where(over[..., None] & (W[..., None] > 0), gp + d * f, P)
            np.maximum(P[..., 2], 0.0, out=P[..., 2])

    def _constraints_native(self, iters):
        P = np.ascontiguousarray(self.P, dtype=np.float64)
        W = np.ascontiguousarray(self.W, dtype=np.float64)
        dp = ctypes.POINTER(ctypes.c_double)
        if self.grab:
            g = self.grab
            patch = np.ascontiguousarray(g["target"] + g["off"] * np.array([1, 1, 0.3]))
            ys, xs = g["ys"], g["xs"]
            tether = np.ascontiguousarray(self.tether, dtype=np.float64)
            NATIVE.cloth_constraints(P.ctypes.data_as(dp), W.ctypes.data_as(dp), self.nx, self.ny,
                                     self.dx, self.dy, iters, self.K_SHEAR, self.K_BEND, 1,
                                     ys.start, ys.stop, xs.start, xs.stop, patch.ctypes.data_as(dp),
                                     g["iy"] * self.nx + g["ix"], tether.ctypes.data_as(dp))
        else:
            NATIVE.cloth_constraints(P.ctypes.data_as(dp), W.ctypes.data_as(dp), self.nx, self.ny,
                                     self.dx, self.dy, iters, self.K_SHEAR, self.K_BEND, 0,
                                     0, 0, 0, 0, None, 0, None)
        self.P = P

    BUMP_H = 10.0
    BUMP_R = 19.0

    def _floor(self):
        """Floor height under each particle: desktop icons hidden under the rug
        make soft bumps (the 'something is under the rug' look)."""
        if self.bumps is None or len(self.bumps) == 0:
            return None
        xy = self.P[..., :2]
        mn = xy.reshape(-1, 2).min(0) - 40
        mx = xy.reshape(-1, 2).max(0) + 40
        b = self.bumps[(self.bumps[:, 0] > mn[0]) & (self.bumps[:, 0] < mx[0]) &
                       (self.bumps[:, 1] > mn[1]) & (self.bumps[:, 1] < mx[1])]
        if len(b) == 0:
            return None
        d2 = ((xy[..., None, :] - b[None, None, :, :]) ** 2).sum(-1)
        return (self.BUMP_H * np.exp(-d2 / (2 * self.BUMP_R ** 2))).max(-1)

    def _separate_layers(self):
        """Binned self-collision / layer separation. Particles are binned in xy
        and sorted by height; any particle that is far from a lower particle of
        the same bin *on the grid* (i.e. belongs to another layer of the rug) is
        lifted to at least one rug thickness above it. The required gap fades in
        with grid distance so the rounded crease itself is not disturbed."""
        P = self.P.reshape(-1, 3)
        h = self.SEP_BIN * max(self.dx, self.dy)
        near_t = self.SEP_NEAR
        iy = self.iy.ravel()
        ix = self.ix.ravel()
        z = P[:, 2]
        newz = z.copy()
        det = np.full(len(P), -1e9)
        flat = np.abs(self.normals().reshape(-1, 3)[:, 2]) > 0.75   # only stacked, lying layers
        contact = np.zeros(len(P), bool)
        for off in self.SEP_OFFSETS:
            bx = np.floor(P[:, 0] / h + off).astype(np.int64)
            by = np.floor(P[:, 1] / h + off).astype(np.int64)
            key = bx * 1000003 + by
            order = np.lexsort((z, key))
            ks = key[order]
            for lag in (1, 2, 3, 4):
                a, b = order[:-lag], order[lag:]
                same = ks[:-lag] == ks[lag:]
                if not same.any():
                    break
                gd = np.maximum(np.abs(iy[a] - iy[b]), np.abs(ix[a] - ix[b]))
                gap = THICK * np.clip((gd - near_t) / 4.0, 0.0, 1.0)
                m = same & (gap > 0) & flat[a] & flat[b]
                if not m.any():
                    continue
                a, b, gap = a[m], b[m], gap[m]
                req = z[a] + gap
                close = z[b] < req + gap * 0.2 + 0.3
                contact[b[close]] = True
                np.maximum.at(newz, b, req)
                np.maximum.at(det, b, req)
        # hysteresis: remember the support height for a few frames so a missed
        # detection (bin boundary, sort order) does not let a layer drop through
        sup = getattr(self, "_support", None)
        if sup is None or sup.shape[0] != len(P):
            sup = np.full(len(P), -1e9)
            self._support_xy = P[:, :2].copy()
        moved_far = np.hypot(*(P[:, :2] - self._support_xy).T) > 0.6 * min(self.dx, self.dy)
        sup = np.where(moved_far, -1e9, sup - 1.2)
        got = det > -1e8
        sup = np.where(got, np.maximum(det, sup), sup)
        self._support_xy[got] = P[got, :2]
        self._support = sup
        newz = np.maximum(newz, sup)
        contact |= sup > -1e8
        lifted = newz > z
        if lifted.any():
            P[:, 2] = newz
            pv = self.prev.reshape(-1, 3)
            pv[lifted, 2] = newz[lifted]
        self.contact = contact.reshape(self.ny, self.nx)

    def step(self, dt=1 / 60, substeps=None, iters=None):
        if substeps is None:
            substeps, iters = (2, 9) if NATIVE is not None else (2, 5)
        if self.sleeping:
            return False
        if self.kinematic:
            self._step_kinematic(dt)
            self._step_fringe(dt)
            return True
        h = dt / substeps
        frame_start = self.P.copy()
        for _ in range(substeps):
            v = (self.P - self.prev) * 0.99
            self.prev = self.P.copy()
            start = self.P.copy()
            self.P = self.P + v
            self.P[..., 2] -= GRAVITY * h * h * (self.W > 0)
            self._constraints(iters)
            floor = self._floor()
            if floor is not None:
                np.maximum(self.P[..., 2], floor, out=self.P[..., 2])
            self._separate_layers()
            # floor contact + positional static/kinetic friction (rugs grip the desk)
            fz = 0.0 if floor is None else floor
            on = ((self.P[..., 2] <= fz + 0.05) | self.contact) & (self.W > 0)
            dxy = self.P[..., :2] - start[..., :2]
            sp = np.hypot(dxy[..., 0], dxy[..., 1])
            stick = on & (sp < 0.45)
            self.P[stick, 0] = start[stick, 0]
            self.P[stick, 1] = start[stick, 1]
            slide = on & ~stick
            self.P[slide, :2] = start[slide, :2] + dxy[slide] * 0.7
            vel = self.P - self.prev
            vel[on, 2] = np.maximum(vel[on, 2], 0)
            vel[on, :2] *= 0.6
            self.prev = self.P - vel
        self._step_fringe(dt)
        # sleep detection (after release: settle, then freeze)
        d = np.abs(self.P - frame_start)
        mv = float(d.max())
        mean = float(d.mean())
        self.last_motion = mv
        if self.grab is None:
            self.since_release = getattr(self, "since_release", 0) + 1
            calm = (mv < 0.05) or (self.since_release > 60 and mean < 0.02 and mv < 0.9)
            self.sleep_frames = self.sleep_frames + 1 if calm else 0
            if self.sleep_frames > 15 or self.since_release > 300:
                self.sleeping = True
                self.prev = self.P.copy()
        else:
            self.since_release = 0
            self.sleep_frames = 0
        return True

    # ------------------------------------------------------------------ presets
    def corner_fold_local(self, fx=0.12, fy=0.02):
        """Analytic diagonal fold of the bottom-right corner, in local coords
        (used as the default 'lifted' state; physics then rounds the crease)."""
        from . import geometry as G
        w, h = self.w, self.h
        p = (fx * w, fy * h)
        m, n = G.fold_line(w, h, p)
        L = np.concatenate([self.rest, np.zeros(self.rest.shape[:-1] + (1,))], -1)
        s = (self.rest[..., 0] - m[0]) * n[0] + (self.rest[..., 1] - m[1]) * n[1]
        flap = s > 0
        nn = np.array(n)
        refl = self.rest - 2 * s[..., None] * nn
        # thick rounded crease: points near the line get lifted on a half-circle
        r = THICK * 0.5
        theta = np.clip(s / (math.pi * r + 1e-9), 0, 1) * math.pi
        L[flap, :2] = refl[flap]
        L[..., 2] = np.where(flap, THICK, 0.0)
        near = flap & (s < math.pi * r)
        L[near, :2] = (self.rest[near] - s[near, None] * nn + (r * np.sin(theta[near]))[:, None] * nn)
        L[near, 2] = r * (1 - np.cos(theta[near]))
        return L

    # ------------------------------------------------------------------ serialisation
    def to_dict(self):
        return dict(nx=self.nx, ny=self.ny, w=self.w, h=self.h,
                    P=np.round(self.P.reshape(-1), 2).tolist())
