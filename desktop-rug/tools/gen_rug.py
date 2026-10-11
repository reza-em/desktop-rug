#!/usr/bin/env python3
"""Procedurally generate the built-in Persian rug texture for Desktop Rug.

100% original procedural artwork (no third-party images) -> free to use (MIT/CC0).
Usage: python tools/gen_rug.py [out.png] [--seed N]
Requires numpy + Pillow (build-time only; the app just loads the PNG).
"""
import sys, math
import numpy as np
from PIL import Image, ImageFilter

SS = 2                       # supersampling factor
W, H = 1500 * SS, 1000 * SS  # rug body (landscape)
FR = 45 * SS                 # fringe length on the short (left/right) ends

C = {k: np.array(v, np.float32) for k, v in dict(
    red=(146, 28, 32), dred=(96, 16, 22), navy=(24, 34, 66), ivory=(234, 219, 180),
    gold=(208, 152, 64), lblue=(84, 118, 160), green=(58, 96, 74), brown=(46, 22, 16),
    pink=(196, 92, 78), orange=(196, 104, 44)).items()}

# Built-in design gallery: same knotted construction, different colourways.
PALETTES = {
    'tabriz': {},                                   # classic red field, navy borders
    'kashan': dict(red=(28, 40, 84), navy=(138, 26, 34), dred=(16, 22, 50), lblue=(178, 72, 62),
                   pink=(200, 120, 90), green=(46, 86, 82)),
    'nain': dict(red=(228, 214, 182), navy=(32, 56, 104), dred=(178, 160, 126), ivory=(248, 241, 220),
                 gold=(112, 136, 172), lblue=(70, 104, 160), green=(96, 120, 146), pink=(150, 164, 190),
                 brown=(38, 46, 66), orange=(120, 140, 170)),
    'qashqai': dict(red=(174, 72, 28), navy=(40, 64, 46), dred=(118, 42, 18), ivory=(240, 216, 160),
                    gold=(228, 172, 58), lblue=(88, 134, 112), green=(150, 118, 38), brown=(62, 30, 14),
                    pink=(210, 120, 60)),
}


def build(seed=7):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    img = np.zeros((H, W, 3), np.float32)
    img[:] = C['red']

    def put(m, col):
        img[m] = C[col]

    d = np.minimum(np.minimum(x, W - 1 - x), np.minimum(y, H - 1 - y))  # distance to edge
    s = SS
    B0, B1, B2, B3, B4, B5, B6 = 10*s, 26*s, 31*s, 128*s, 133*s, 156*s, 161*s

    # ---- guard & binding ------------------------------------------------------
    put(d < B0, 'brown')
    m = (d >= B0) & (d < B1); put(m, 'ivory')
    # along-edge coordinate for chains
    side_t = np.where(np.minimum(x, W-1-x) < np.minimum(y, H-1-y), y, x)
    per = 16 * s
    tt = (side_t % per) - per / 2
    nn = d - (B0 + B1) / 2
    put(m & (np.abs(tt) + np.abs(nn) < 5 * s), 'red')
    put((d >= B1) & (d < B2), 'navy')

    # ---- main border ------------------------------------------------------------
    band = (d >= B2) & (d < B3)
    put(band, 'navy')
    bw = B3 - B2
    nmid = B2 + bw / 2
    n = d - nmid                                  # across-band coordinate (-bw/2..bw/2)
    # corner squares vs sides
    inx = (x >= B3) & (x < W - B3)
    iny = (y >= B3) & (y < H - B3)
    horiz = band & inx                            # top/bottom side
    vert = band & iny & ~inx                      # left/right side
    corner = band & ~inx & ~iny
    for mask, t0, L, tcoord in ((horiz, B3, W - 2*B3, x), (vert, B3, H - 2*B3, y)):
        cnt = max(1, round(L / (150 * s)))
        p = L / cnt
        t = tcoord - t0
        k = np.floor(t / p)
        lt = t - (k + 0.5) * p                    # local coord along band
        alt = (k % 2 == 0)
        # vine
        vine = np.abs(n - 0.28*bw*np.sin(2*np.pi*t/p)) < 3.2*s
        put(mask & vine, 'gold')
        # leaves along vine
        lv = ((lt + p/2) % (p/2)) - p/4
        leaf = (lv/(18*s))**2 + ((n + 0.30*bw*np.cos(2*np.pi*t/p))/(7*s))**2 < 1
        put(mask & leaf & ~vine, 'green')
        r = np.hypot(lt, n); th = np.arctan2(n, lt)
        R = 0.40 * bw
        petal = r < R * (0.62 + 0.38*np.abs(np.cos(4*th)))
        put(mask & petal & alt, 'red'); put(mask & petal & ~alt, 'ivory')
        put(mask & (r < R*0.58*(0.7+0.3*np.abs(np.cos(4*th+np.pi/4)))) & alt, 'ivory')
        put(mask & (r < R*0.58*(0.7+0.3*np.abs(np.cos(4*th+np.pi/4)))) & ~alt, 'lblue')
        put(mask & (r < R*0.30), 'gold')
        put(mask & (r < R*0.13), 'dred')
        put(mask & petal & (np.abs(r - R*(0.62 + 0.38*np.abs(np.cos(4*th)))) < 2.0*s), 'brown')
    # corner rosettes
    for cx0, cy0 in ((nmid, nmid), (W-1-nmid, nmid), (nmid, H-1-nmid), (W-1-nmid, H-1-nmid)):
        dx, dy = x - cx0, y - cy0
        r = np.hypot(dx, dy); th = np.arctan2(dy, dx)
        R = 0.46 * bw
        put(corner & (r < R*(0.7+0.3*np.abs(np.cos(6*th)))), 'ivory')
        put(corner & (r < R*0.62*(0.75+0.25*np.abs(np.cos(6*th+np.pi/6)))), 'red')
        put(corner & (r < R*0.30), 'gold')
        put(corner & (r < R*0.12), 'navy')
    put((d >= B3) & (d < B4), 'ivory')
    # inner guard: red w/ gold diamonds
    g = (d >= B4) & (d < B5)
    put(g, 'dred')
    tt = (side_t % (22*s)) - 11*s
    nn = d - (B4 + B5)/2
    put(g & (np.abs(tt) + np.abs(nn) < 8*s), 'gold')
    put(g & (np.abs(tt) + np.abs(nn) < 3.5*s), 'navy')
    put((d >= B5) & (d < B6), 'navy')

    # ---- field ------------------------------------------------------------------
    field = d >= B6
    cx, cy = W/2, H/2
    # arabesque vine lattice
    k1 = 2*np.pi/(120*s)
    a = np.sin(x*k1) + np.sin(y*k1) + 0.6*np.sin((x+y)*k1*0.5)
    put(field & (np.abs(a) < 0.07), 'dred')
    b = np.sin((x-y)*k1*0.5) * np.cos((x+y)*k1*0.5)
    put(field & (np.abs(b - 0.55) < 0.035), 'gold')
    # small flowers on a diamond lattice
    sp = 120*s
    u = (x - cx + sp/2) % sp - sp/2
    v = (y - cy + sp/2) % sp - sp/2
    u2 = (x - cx) % sp - sp/2
    v2 = (y - cy) % sp - sp/2
    for uu, vv, c1, c2 in ((u, v, 'ivory', 'navy'), (u2, v2, 'navy', 'gold')):
        r = np.hypot(uu, vv); th = np.arctan2(vv, uu)
        put(field & (r < 17*s*(0.6+0.4*np.abs(np.cos(4*th)))), c1)
        put(field & (r < 7*s), c2)
        put(field & (r < 3*s), 'red')
    # leaves
    lu = (x - cx + sp/4) % (sp/2) - sp/4
    lv = (y - cy) % (sp/2) - sp/4
    put(field & ((lu/(4*s))**2 + (lv/(11*s))**2 < 1), 'green')

    # corner spandrels
    fw, fh = (W - 2*B6), (H - 2*B6)
    for sx, sy in ((B6, B6), (W-1-B6, B6), (B6, H-1-B6), (W-1-B6, H-1-B6)):
        dx, dy = np.abs(x - sx)/(0.22*fw), np.abs(y - sy)/(0.30*fh)
        sd = np.sqrt(dx**2 + dy**2)
        th = np.arctan2(dy, dx)
        edge = 1 - 0.07*np.cos(14*th)
        m = field & (sd < edge)
        put(field & (sd < edge + 0.05), 'ivory')
        put(m, 'navy')
        put(m & (np.abs(sd - 0.7*edge) < 0.025), 'gold')
        put(m & (np.abs(np.sin(9*th + sd*6)) < 0.12) & (sd < 0.62), 'lblue')
        put(m & (np.abs(np.sin(9*th - sd*6)) < 0.10) & (sd < 0.62), 'pink')
        put(m & (np.hypot(dx, dy) < 0.16), 'red')
        put(m & (np.hypot(dx, dy) < 0.08), 'gold')

    # central medallion (long axis horizontal)
    A, Bm = 0.27*fw, 0.38*fh
    p, q = (x - cx)/A, (y - cy)/Bm
    th = np.arctan2(q, p)
    sm = 0.55*(np.abs(p) + np.abs(q)) + 0.45*np.hypot(p, q)
    sm = sm * (1 + 0.045*np.cos(16*th))
    put(field & (sm < 1.06), 'ivory')
    put(field & (sm < 1.0), 'navy')
    put(field & (sm < 0.93) , 'ivory')
    put(field & (sm < 0.90), 'red')
    # floral swirls inside medallion
    rr = np.hypot(p, q)
    put(field & (sm < 0.88) & (sm > 0.55) & (np.abs(np.sin(8*th + 7*rr)) < 0.13), 'gold')
    put(field & (sm < 0.88) & (sm > 0.55) & (np.abs(np.sin(8*th - 7*rr)) < 0.11), 'ivory')
    star = (0.5*(np.abs(p)+np.abs(q)) + 0.5*np.maximum(np.abs(p), np.abs(q))) * (1 + 0.12*np.cos(8*th))
    put(field & (star < 0.52), 'navy')
    put(field & (star < 0.47), 'ivory')
    put(field & (star < 0.42), 'lblue')
    put(field & (star < 0.42) & (np.abs(np.sin(12*th)) < 0.25), 'navy')
    put(field & (rr < 0.22*(0.8+0.2*np.abs(np.cos(6*th)))), 'red')
    put(field & (rr < 0.13*(0.75+0.25*np.abs(np.cos(8*th)))), 'gold')
    put(field & (rr < 0.05), 'navy')
    # pendants along long axis
    for sgn in (-1, 1):
        pp, qq = (x - (cx + sgn*1.16*A))/(0.12*A), (y - cy)/(0.20*Bm)
        ps = np.abs(pp)*0.8 + np.abs(qq)
        put(field & (ps < 1.08), 'ivory')
        put(field & (ps < 1.0), 'navy')
        put(field & (ps < 0.55), 'gold')
        put(field & (ps < 0.25), 'red')
        # stem connecting pendant to medallion
        put(field & (np.abs(y - cy) < 4*s) & (np.abs(x - cx) > 0.98*A) & (np.abs(x - cx) < 1.06*A), 'navy')

    # ---- downsample & wool texture ------------------------------------------------
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((W//SS, H//SS), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    knot = 2
    kn = rng.normal(0, 1, (h//knot + 1, w//knot + 1)).astype(np.float32)
    kn = np.kron(kn, np.ones((knot, knot), np.float32))[:h, :w]
    pix = rng.normal(0, 1, (h, w)).astype(np.float32)
    rows = np.cumsum(rng.normal(0, 1, h)).astype(np.float32)
    rows = (rows - rows.mean()) / (rows.std() + 1e-6)
    abrash = np.convolve(rows, np.ones(25)/25, mode='same')[:, None]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    weave = 0.025*np.sin(xx*np.pi/1.0) * np.sin(yy*np.pi/1.0)
    vign = 1 - 0.10*(((xx - w/2)/(w/2))**2 + ((yy - h/2)/(h/2))**2)
    wear = Image.fromarray((rng.random((h//40+1, w//40+1))*255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    wear = np.asarray(wear).astype(np.float32)/255
    f = (1 + 0.055*kn + 0.035*pix + 0.035*abrash + weave) * vign * (0.95 + 0.08*wear)
    a = a * f[..., None]
    a = np.clip(a, 0, 255)
    body = Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.UnsharpMask(1, 40, 0))

    # ---- fringe on short ends -------------------------------------------------------
    fr = FR // SS
    out = Image.new('RGBA', (w + 2*fr, h), (0, 0, 0, 0))
    fa = np.zeros((h, fr, 4), np.float32)
    for yy0 in range(0, h, 4):
        L = int(fr * (0.75 + 0.25*rng.random()))
        shade = 0.85 + 0.2*rng.random()
        wob = rng.normal(0, 0.8)
        for xx0 in range(L):
            yc = yy0 + 1 + wob*(xx0/fr)
            for dy in (-1, 0, 1):
                yi = int(round(yc)) + dy
                if 0 <= yi < h:
                    al = 255 if dy == 0 else 120
                    col = C['ivory']*shade*(0.9 if dy else 1.0)*(1 - 0.15*xx0/fr)
                    fa[yi, xx0, :3] = col
                    fa[yi, xx0, 3] = max(fa[yi, xx0, 3], al)
    fr_img = Image.fromarray(fa.astype(np.uint8), 'RGBA')
    out.paste(fr_img.transpose(Image.FLIP_LEFT_RIGHT), (0, 0))
    out.paste(fr_img, (w + fr, 0))
    out.paste(body.convert('RGBA'), (fr, 0))
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('out', nargs='?')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--palette', default='tabriz', choices=sorted(PALETTES))
    a = ap.parse_args()
    for k, v in PALETTES[a.palette].items():
        C[k] = np.array(v, np.float32)
    outp = a.out or ('desktop_rug/assets/rug_default.png' if a.palette == 'tabriz'
                     else 'desktop_rug/assets/rug_%s.png' % a.palette)
    im = build(a.seed)
    im.save(outp, optimize=True)
    print('wrote', outp, im.size)
