#!/usr/bin/env python3
"""Draw assets/og.png, the 1200x630 card social platforms and search results show.

    python scripts/make_og.py

Drawn rather than screenshotted so it can be regenerated when the wording
changes, and committed rather than built by CI so the URL in every page's
meta tags is never a 404 waiting on a build. Pillow is already a dependency of
the converter, so this costs nothing extra.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1200, 630
BG = (14, 16, 19)
INK = (232, 234, 237)
SOFT = (150, 157, 166)
ACCENT = (255, 106, 77)
LINE = (35, 39, 45)


def font(names, size):
    """The first of `names` this machine has, else Pillow's built-in bitmap.

    A missing font must not fail the build: the card still renders, just
    plainer, and a CI box has a different set installed from a desktop.
    """
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


SANS = ['segoeuib.ttf', 'DejaVuSans-Bold.ttf', 'Arial Bold.ttf', 'arialbd.ttf']
SANS_R = ['segoeui.ttf', 'DejaVuSans.ttf', 'Arial.ttf', 'arial.ttf']
MONO = ['consola.ttf', 'DejaVuSansMono.ttf', 'Menlo.ttc', 'cour.ttf']


def main():
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)

    # A hairline grid, faint enough to read as texture rather than as content.
    for x in range(0, W, 40):
        d.line([(x, 0), (x, H)], fill=(18, 21, 25))
    for y in range(0, H, 40):
        d.line([(0, y), (W, y)], fill=(18, 21, 25))
    d.rectangle([0, 0, W - 1, 7], fill=ACCENT)

    pad = 80
    d.text((pad, 96), 'assetto-corsa-gltf', font=font(MONO, 30), fill=ACCENT)

    big = font(SANS, 68)
    d.text((pad, 156), 'Assetto Corsa models,', font=big, fill=INK)
    d.text((pad, 236), 'as glTF 2.0', font=big, fill=INK)

    sub = font(SANS_R, 30)
    d.text((pad, 344),
           'Convert .kn5 cars and tracks to glTF or a single GLB —',
           font=sub, fill=SOFT)
    d.text((pad, 386),
           'node hierarchy, liveries and PBR materials intact.',
           font=sub, fill=SOFT)

    d.line([(pad, 462), (W - pad, 462)], fill=LINE, width=2)

    mono = font(MONO, 26)
    d.text((pad, 496), '$ pip install assetto-corsa-gltf', font=mono, fill=SOFT)
    d.text((pad, 536), '$ kn5-to-gltf car.kn5 out --glb', font=mono, fill=INK)

    out = os.path.join(ROOT, 'assets', 'og.png')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, 'PNG', optimize=True)
    print('wrote %s  (%d x %d, %.0f KB)'
          % (out, W, H, os.path.getsize(out) / 1024))


if __name__ == '__main__':
    sys.exit(main() or 0)
