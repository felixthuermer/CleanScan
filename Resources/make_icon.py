#!/usr/bin/env python3
"""Generate Resources/AppIcon.icns for DocDigitizer.

Run with any Python that has Pillow + NumPy (e.g. the backend venv):
    ../Backend/.venv/bin/python make_icon.py
Requires macOS `iconutil` (part of the Command Line Tools) to build the .icns.
"""
from __future__ import annotations
import os
import subprocess

from PIL import Image, ImageDraw
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024


def build_master() -> Image.Image:
    # vertical gradient background
    top = np.array([79, 110, 247], dtype=np.float32)     # indigo
    bot = np.array([13, 165, 233], dtype=np.float32)      # sky blue
    grad = np.zeros((S, S, 3), np.uint8)
    for y in range(S):
        t = y / (S - 1)
        grad[y, :, :] = (top * (1 - t) + bot * t).astype(np.uint8)
    bg = Image.fromarray(grad, "RGB").convert("RGBA")

    # rounded-square mask (macOS-style)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1],
                                           radius=int(S * 0.225), fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(icon)
    dw, dh = int(S * 0.42), int(S * 0.54)
    dx, dy = (S - dw) // 2, int(S * 0.18)
    rad = int(S * 0.03)
    d.rounded_rectangle([dx + 14, dy + 18, dx + dw + 14, dy + dh + 18],
                        radius=rad, fill=(0, 0, 0, 55))                # shadow
    d.rounded_rectangle([dx, dy, dx + dw, dy + dh], radius=rad,
                        fill=(255, 255, 255, 255))                    # sheet

    lx = dx + int(dw * 0.14)
    rx = dx + int(dw * 0.86)
    ly = dy + int(dh * 0.20)
    gap = int(dh * 0.12)
    lh = int(dh * 0.045)
    for i in range(4):
        yy = ly + i * gap
        x2 = rx if i % 2 == 0 else dx + int(dw * 0.60)
        d.rounded_rectangle([lx, yy, x2, yy + lh], radius=lh // 2,
                            fill=(150, 160, 180, 255))                # text lines

    # green check badge (bottom-right of the sheet)
    br = int(S * 0.11)
    bcx, bcy = dx + dw - int(dw * 0.01), dy + dh - int(dh * 0.01)
    d.ellipse([bcx - br, bcy - br, bcx + br, bcy + br], fill=(34, 197, 94, 255))
    cw = br * 0.9
    d.line([(bcx - cw * 0.45, bcy + cw * 0.02),
            (bcx - cw * 0.10, bcy + cw * 0.38),
            (bcx + cw * 0.50, bcy - cw * 0.40)],
           fill=(255, 255, 255, 255), width=int(br * 0.22), joint="curve")
    return icon


def main() -> None:
    icon = build_master()
    iconset = os.path.join(HERE, "AppIcon.iconset")
    os.makedirs(iconset, exist_ok=True)
    for s in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = s * scale
            name = f"icon_{s}x{s}{'@2x' if scale == 2 else ''}.png"
            icon.resize((px, px), Image.LANCZOS).save(os.path.join(iconset, name))
    subprocess.run(["iconutil", "-c", "icns",
                    "-o", os.path.join(HERE, "AppIcon.icns"), iconset], check=True)
    # a PNG for the README (GitHub can't render .icns)
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "icon.png"))
    print("wrote AppIcon.icns + icon.png")


if __name__ == "__main__":
    main()
