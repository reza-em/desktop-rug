#!/usr/bin/env python3
"""Procedurally generate the bundled floor wallpapers (original artwork, CC0).
Usage: python tools/gen_floors.py [--w 2560 --h 1440]   (needs numpy + Pillow)
Writes desktop_rug/assets/floors/{parquet_light,wood_dark,stone_tiles,carpet}.jpg"""
import argparse, os
import numpy as np
from PIL import Image, ImageFilter

OUT = os.path.join(os.path.dirname(__file__), '..', 'desktop_rug', 'assets', 'floors')


def noise(rng, h, w, scale, sx=None):
    """Smooth value noise in [-1, 1] (scale = feature size in px, optional x scale)."""
    sx = sx or scale
    a = rng.random((max(2, int(h / scale) + 2), max(2, int(w / sx) + 2))).astype(np.float32)
    im = Image.fromarray(a, 'F').resize((w, h), Image.BICUBIC)
    return np.asarray(im, np.float32) * 2.0 - 1.0


def planks(rng, H, W, ph, base, var, gap_col, min_len, max_len, grain_k):
    img = np.zeros((H, W, 3), np.float32)
    y = np.arange(H)[:, None].astype(np.float32)
    rows = int(np.ceil(H / ph))
    fine = noise(rng, H, W, 3, 40)
    for r in range(rows):
        y0, y1 = r * ph, min(H, (r + 1) * ph)
        x = -rng.integers(0, max_len)
        while x < W:
            L = int(rng.integers(min_len, max_len))
            xa, xb = max(0, x), min(W, x + L)
            if xb > xa:
                tone = np.array(base, np.float32) * (1 + rng.normal(0, var)) + rng.normal(0, 2.0, 3)
                h, l = y1 - y0, xb - xa
                streak = noise(rng, h, l, 1.6, rng.uniform(80, 200))      # long fibres
                band = noise(rng, h, l, 7, rng.uniform(250, 600))         # wide grain bands
                shade = 1 + grain_k * (0.6 * streak + 0.45 * band) + 0.03 * fine[y0:y1, xa:xb]
                img[y0:y1, xa:xb] = tone * shade[..., None]
                img[y0:y1, xa:xa + 2] = gap_col                       # butt joint
            x += L
        img[y0:y0 + 2, :] = gap_col                                     # long seam
        img[y0 + 2:y0 + 4, :] *= 1.06                                   # bevel highlight
    return img


def light_parquet(rng, H, W):
    return planks(rng, H, W, 92, (204, 152, 100), 0.06, (118, 80, 50), 420, 1100, 0.12)


def dark_wood(rng, H, W):
    return planks(rng, H, W, 140, (92, 56, 36), 0.08, (36, 22, 14), 700, 1700, 0.16)


def stone_tiles(rng, H, W):
    T, G = 300, 6
    img = np.zeros((H, W, 3), np.float32)
    big = noise(rng, H, W, 120)
    mid = noise(rng, H, W, 30)
    vein = np.abs(noise(rng, H, W, 160) + 0.5 * noise(rng, H, W, 50))
    vein = np.exp(-(vein * 55) ** 2)
    base = np.array((214, 204, 186), np.float32)
    for ty in range(0, H, T):
        for tx in range(0, W, T):
            tone = base * (1 + rng.normal(0, 0.025)) + rng.normal(0, 1.2, 3)
            sl = (slice(ty, min(H, ty + T)), slice(tx, min(W, tx + T)))
            s = 1 + 0.04 * big[sl] + 0.025 * mid[sl] - 0.10 * vein[sl]
            img[sl] = tone * s[..., None]
    yy, xx = np.mgrid[0:H, 0:W]
    grout = ((yy % T) < G) | ((xx % T) < G)
    img[grout] = (150, 142, 130)
    edge = ((yy % T) == G) | ((xx % T) == G)
    img[edge] *= 1.08
    return img


def carpet(rng, H, W):
    base = np.array((112, 116, 124), np.float32)
    fib = rng.normal(0, 1, (H, W)).astype(np.float32)
    fib = np.asarray(Image.fromarray(((fib * 30) + 128).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7)), np.float32) / 128 - 1
    mot = noise(rng, H, W, 60) * 0.5 + noise(rng, H, W, 12) * 0.3
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    tuft = 0.5 + 0.5 * np.sin(xx * 1.9) * np.sin(yy * 1.9)
    s = 1 + 0.10 * fib + 0.05 * mot + 0.03 * tuft
    img = base * s[..., None]
    img[..., 2] *= 1.02
    return img


FLOORS = dict(parquet_light=light_parquet, wood_dark=dark_wood, stone_tiles=stone_tiles, carpet=carpet)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--w', type=int, default=2560)
    ap.add_argument('--h', type=int, default=1440)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    for i, (name, fn) in enumerate(FLOORS.items()):
        rng = np.random.default_rng(11 + i)
        img = fn(rng, a.h, a.w)
        # gentle vignette so desktop icons/rug read well
        yy, xx = np.mgrid[0:a.h, 0:a.w].astype(np.float32)
        v = 1 - 0.18 * (((xx / a.w - 0.5) ** 2 + (yy / a.h - 0.5) ** 2) * 2)
        img = (img * v[..., None]).clip(0, 255).astype(np.uint8)
        p = os.path.join(OUT, name + '.jpg')
        Image.fromarray(img).save(p, quality=86, optimize=True, progressive=True)
        print('wrote', p)
