/* Desktop Rug - tiny compiled helper for the cloth constraint solver.
 * Pure C99, no dependencies. Loaded with ctypes; the app falls back to a
 * numpy implementation if this library is missing.
 *   Linux:   gcc -O2 -shared -fPIC -o libclothsim.so clothsim.c -lm
 *   Windows: x86_64-w64-mingw32-gcc -O2 -shared -static-libgcc -o clothsim.dll clothsim.c
 */
#include <math.h>
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

static inline void pair(double *P, const double *W, int a, int b, double rest, double k, int compress_only)
{
    double wa = W[a], wb = W[b], ws = wa + wb;
    if (ws <= 0.0) return;
    double *pa = P + 3 * a, *pb = P + 3 * b;
    double dx = pb[0] - pa[0], dy = pb[1] - pa[1], dz = pb[2] - pa[2];
    double L = sqrt(dx * dx + dy * dy + dz * dz) + 1e-9;
    double diff = (L - rest) / L;
    if (compress_only && diff > 0.0) return;
    double s = diff * k / ws;
    double sa = s * wa, sb = s * wb;
    pa[0] += dx * sa; pa[1] += dy * sa; pa[2] += dz * sa;
    pb[0] -= dx * sb; pb[1] -= dy * sb; pb[2] -= dz * sb;
}

static void sweep(double *P, const double *W, int nx, int ny, double dx, double dy, double dd,
                  double ks, double kb, int x, int y)
{
    int i = y * nx + x;
    if (x < nx - 1) pair(P, W, i, i + 1, dx, 1.0, 0);
    if (y < ny - 1) pair(P, W, i, i + nx, dy, 1.0, 0);
    if (x < nx - 1 && y < ny - 1) {
        pair(P, W, i, i + nx + 1, dd, ks, 0);
        pair(P, W, i + 1, i + nx, dd, ks, 0);
    }
    if (x < nx - 2) pair(P, W, i, i + 2, 2 * dx, kb, 1);
    if (y < ny - 2) pair(P, W, i, i + 2 * nx, 2 * dy, kb, 1);
}

/* patch: positions (3 per particle) for the pinned rectangle [y0,y1) x [x0,x1)
 * tether: per particle max distance from grabbed particle gi (only if grab). */
EXPORT void cloth_constraints(double *P, const double *W, int nx, int ny, double dx, double dy,
                              int iters, double ks, double kb, int grab, int y0, int y1, int x0,
                              int x1, const double *patch, int gi, const double *tether)
{
    double dd = sqrt(dx * dx + dy * dy);
    int n = nx * ny;
    for (int it = 0; it < iters; ++it) {
        if (it & 1) {
            for (int y = ny - 1; y >= 0; --y)
                for (int x = nx - 1; x >= 0; --x) sweep(P, W, nx, ny, dx, dy, dd, ks, kb, x, y);
        } else {
            for (int y = 0; y < ny; ++y)
                for (int x = 0; x < nx; ++x) sweep(P, W, nx, ny, dx, dy, dd, ks, kb, x, y);
        }
        if (grab) {
            int k = 0;
            for (int y = y0; y < y1; ++y)
                for (int x = x0; x < x1; ++x, ++k) {
                    double *p = P + 3 * (y * nx + x);
                    p[0] = patch[3 * k]; p[1] = patch[3 * k + 1]; p[2] = patch[3 * k + 2];
                }
            double *g = P + 3 * gi;
            for (int i = 0; i < n; ++i) {
                if (W[i] <= 0.0) continue;
                double *p = P + 3 * i;
                double ddx = p[0] - g[0], ddy = p[1] - g[1], ddz = p[2] - g[2];
                double L = sqrt(ddx * ddx + ddy * ddy + ddz * ddz) + 1e-9;
                if (L > tether[i]) {
                    double f = tether[i] / L;
                    p[0] = g[0] + ddx * f; p[1] = g[1] + ddy * f; p[2] = g[2] + ddz * f;
                }
            }
        }
        for (int i = 0; i < n; ++i)
            if (P[3 * i + 2] < 0.0) P[3 * i + 2] = 0.0;
    }
}
