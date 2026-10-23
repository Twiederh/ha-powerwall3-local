"""Original icon: wall battery with charge bolt and sun (no third-party marks)."""
import math, sys
from PIL import Image, ImageDraw

S = 2048  # supersampled canvas

def draw(body, bolt, sun):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Sun (top left)
    cx, cy, r = 470, 470, 210
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=sun)
    for i in range(8):
        a = math.radians(i * 45)
        x1, y1 = cx + math.cos(a) * (r + 70), cy + math.sin(a) * (r + 70)
        x2, y2 = cx + math.cos(a) * (r + 190), cy + math.sin(a) * (r + 190)
        d.line([x1, y1, x2, y2], fill=sun, width=80)
        d.ellipse([x1 - 40, y1 - 40, x1 + 40, y1 + 40], fill=sun)
        d.ellipse([x2 - 40, y2 - 40, x2 + 40, y2 + 40], fill=sun)
    # Battery body + terminal
    d.rounded_rectangle([1000, 380, 1360, 520], radius=50, fill=body)
    d.rounded_rectangle([760, 470, 1600, 1960], radius=170, fill=body)
    # Charge bolt
    bx, by = 1180, 1215
    pts = [(bx + 90, by - 520), (bx - 250, by + 70), (bx - 20, by + 70),
           (bx - 110, by + 540), (bx + 250, by - 80), (bx + 20, by - 80)]
    d.polygon(pts, fill=bolt)
    return im

def finish(im, path, size):
    box = im.getbbox()
    im = im.crop(box)
    w, h = im.size
    side = max(w, h)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(im, ((side - w) // 2, (side - h) // 2))
    sq.resize((size, size), Image.LANCZOS).save(path, optimize=True)

out = sys.argv[1]
light = draw(body=(43, 47, 54, 255), bolt=(61, 190, 90, 255), sun=(245, 166, 35, 255))
dark = draw(body=(221, 225, 231, 255), bolt=(46, 158, 74, 255), sun=(245, 166, 35, 255))
for img, prefix in ((light, ""), (dark, "dark_")):
    finish(img, f"{out}/{prefix}icon.png", 256)
    finish(img, f"{out}/{prefix}icon@2x.png", 512)
print("ok")
