#!/usr/bin/env python3
"""Make app icons (PNG + ICO) from the centre medallion of the built-in rug."""
from PIL import Image, ImageDraw
im = Image.open("desktop_rug/assets/rug_default.png").convert("RGBA")
w, h = im.size
s = int(h * 0.62)
crop = im.crop((w // 2 - s // 2, h // 2 - s // 2, w // 2 + s // 2, h // 2 + s // 2)).resize((256, 256), Image.LANCZOS)
mask = Image.new("L", (256, 256), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, 255, 255), 48, fill=255)
out = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
out.paste(crop, (0, 0), mask)
out.save("desktop_rug/assets/icon.png")
out.save("packaging/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icons written")
