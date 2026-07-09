"""Generate all FlowSpeech icons with Pillow.

Outputs (into assets/):
  FlowSpeech.icns              — app icon (Dock, Finder)
  menubar_idle@2x.png          — template menu bar icon: waveform
  menubar_recording@2x.png     — template icon: filled dot + waveform
  menubar_processing@2x.png    — template icon: three dots

Template icons are pure black with alpha; macOS recolors them for
light/dark menu bars (rumps `template=True`).

Run:  python assets/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent

# Waveform bar heights as a fraction of full height (symmetric around center).
WAVE = (0.30, 0.55, 0.90, 0.65, 1.0, 0.5, 0.80, 0.40)


def _draw_wave(draw, cx, cy, width, height, bar_w, gap, color, heights=WAVE):
    n = len(heights)
    total = n * bar_w + (n - 1) * gap
    x = cx - total / 2
    for h in heights:
        bh = height * h
        draw.rounded_rectangle(
            [x, cy - bh / 2, x + bar_w, cy + bh / 2],
            radius=bar_w / 2,
            fill=color,
        )
        x += bar_w + gap


def make_app_icon() -> Image.Image:
    """1024×1024 rounded square, indigo gradient, white waveform."""
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # Vertical gradient indigo → violet.
    top, bottom = (63, 81, 251), (139, 92, 246)
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / size
        gd.line(
            [(0, y), (size, y)],
            fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,),
        )

    # macOS squircle-ish mask.
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    margin = int(size * 0.08)
    md.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=int(size * 0.20),
        fill=255,
    )
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    _draw_wave(
        d, size / 2, size / 2,
        width=size * 0.6, height=size * 0.42,
        bar_w=size * 0.052, gap=size * 0.036,
        color=(255, 255, 255, 255),
    )
    return img


def make_menubar_icon(kind: str) -> Image.Image:
    """36×36 (@2x for 18pt) black template icon."""
    size = 36
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    black = (0, 0, 0, 255)

    if kind == "idle":
        _draw_wave(d, size / 2, size / 2, size, size * 0.72, 3, 2, black)
    elif kind == "recording":
        # Filled circle — unmistakable "on air".
        r = size * 0.30
        d.ellipse([size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r], fill=black)
    elif kind == "processing":
        r = 3.2
        for i, x in enumerate((size * 0.22, size * 0.5, size * 0.78)):
            d.ellipse([x - r, size / 2 - r, x + r, size / 2 + r], fill=black)
    else:
        raise ValueError(kind)
    return img


def main() -> None:
    app = make_app_icon()
    # Pillow writes .icns directly; include all standard sizes.
    app.save(
        HERE / "FlowSpeech.icns",
        sizes=[(s, s) for s in (16, 32, 64, 128, 256, 512, 1024)],
    )
    app.resize((512, 512)).save(HERE / "app_icon.png")

    for kind in ("idle", "recording", "processing"):
        make_menubar_icon(kind).save(HERE / f"menubar_{kind}@2x.png")

    print("Icons written to", HERE)


if __name__ == "__main__":
    main()
