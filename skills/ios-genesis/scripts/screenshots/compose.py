#!/usr/bin/env python3
"""Compose captioned App Store screenshots and creatives from simulator raws.

A template, generalized from Cadenza's make_shots.py (3.0.0). The look (fonts,
colors, layout geometry) is project-specific: copy this file and a shots.json
into the target repo (docs/appstore-screenshots/) and change the config first,
the code only when a layout really needs it.

  python3 compose.py shots.json                 # every set
  python3 compose.py shots.json --set v1-en-US  # one set
  python3 compose.py shots.json --verify        # sizes and alpha of everything rendered

Requires Pillow (`pip install pillow`).

Per set (see shots.example.json):
  layout "portrait"  caption on top, the screen in a phone frame bleeding off the
                     bottom (iPhone sets, Duo outer display)
  layout "side"      caption left, the framed screen right (Duo open display,
                     product page header 3840x1646, search result 3840x2560)
  slots              [[w, h, dir], ...]. With "derive": true (portrait default)
                     the first slot is composed and the others are scaled to
                     width and center-cropped from it, never re-composed, so
                     every size shows the same shot.

What every raw gets, before composition:
  status bar         cropped off the top (strip_status_bar, default on for
                     portrait), keeping a small margin above the content.
                     iPhone only: iPhone Duo puts its indicators at the side
                     of the outer display and the corner of the open one, so
                     Duo sets set "strip_status_bar": false (a top crop clips
                     the screen's title)
  redact             [[x0, y0, x1, y1], ...] boxes in the raw's own pixels are
                     pixelated and blurred: creator handles, faces, anyone's
                     content you don't have permission to advertise with
                     (Guideline 5.2)

Output is RGB with no alpha channel; App Store Connect rejects transparency.
Screenshots must show the real app (Guideline 2.3.3) and no other platform's
name or logo, so captions never name one either.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FALLBACK_FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/System/Library/Fonts/Helvetica.ttc",
                  "/Library/Fonts/Arial.ttf"]


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


class Style:
    def __init__(self, cfg: dict, base: Path):
        c = cfg.get("colors", {})
        self.background = hex_rgb(c.get("background", "#0A0B0D"))
        self.text = hex_rgb(c.get("text", "#FFFFFF"))
        self.subline = hex_rgb(c.get("subline", "#BDBEC0"))
        self.frame = hex_rgb(c.get("frame", "#1B1C21"))
        self.ring = hex_rgb(c.get("ring", "#2A2C33"))
        self.accent = hex_rgb(c.get("accent", "#00DFE8"))
        # A font entry is a path, or {"path": ..., "weight": 700} for a
        # variable font (its default instance is often the thinnest).
        fonts = {k: (v if isinstance(v, dict) else {"path": v}) for k, v in cfg.get("fonts", {}).items()}
        self.font_paths = {k: base / v["path"] for k, v in fonts.items()}
        self.font_weights = {k: v["weight"] for k, v in fonts.items() if "weight" in v}
        sb = cfg.get("status_bar", {})
        self.status_crop = sb.get("crop_fraction", 0.062)
        self.status_margin = sb.get("top_margin_fraction", 0.03)
        self.redact_pixel = cfg.get("redact", {}).get("pixel_size", 18)
        self.redact_blur = cfg.get("redact", {}).get("blur_radius", 10)

    def font(self, role: str, size: int) -> ImageFont.FreeTypeFont:
        candidates = [self.font_paths.get(role)] + [Path(p) for p in FALLBACK_FONTS]
        for path in candidates:
            if path and path.exists():
                font = ImageFont.truetype(str(path), size)
                if role in self.font_weights and path == self.font_paths.get(role):
                    try:
                        axes = font.get_variation_axes()
                        font.set_variation_by_axes([self.font_weights[role] if a.get("name") in (b"Weight", "Weight")
                                                    else a["default"] for a in axes])
                    except OSError:
                        pass  # not a variable font
                return font
        return ImageFont.load_default(size)


# ---------------------------------------------------------------- raw prep

def redact(img: Image.Image, boxes: list, style: Style) -> Image.Image:
    img = img.copy()
    for box in boxes:
        x0, y0, x1, y1 = (int(v) for v in box)
        region = img.crop((x0, y0, x1, y1))
        small = region.resize((max(1, region.width // style.redact_pixel),
                               max(1, region.height // style.redact_pixel)), Image.BILINEAR)
        region = small.resize(region.size, Image.NEAREST).filter(ImageFilter.GaussianBlur(style.redact_blur))
        img.paste(region, (x0, y0))
    return img


def strip_status_bar(img: Image.Image, style: Style) -> Image.Image:
    """Crop the status bar off the top, then keep a margin above the content
    (filled with the first content row) so the screen doesn't start flush."""
    w, h = img.size
    body = img.crop((0, round(h * style.status_crop), w, h))
    margin = round(h * style.status_margin)
    out = Image.new("RGB", (w, body.height + margin))
    out.paste(body.crop((0, 0, w, 1)).resize((w, margin)), (0, 0))
    out.paste(body, (0, margin))
    return out


def load_raw(shot: dict, raw_dir: Path, style: Style, strip_default: bool) -> Image.Image:
    path = raw_dir / shot["raw"]
    if not path.exists():
        sys.exit(f"missing raw {path} (capture it first, or drop in the device capture)")
    img = Image.open(path).convert("RGB")
    if shot.get("redact"):
        img = redact(img, shot["redact"], style)
    if shot.get("strip_status_bar", strip_default):
        img = strip_status_bar(img, style)
    return img


# ---------------------------------------------------------------- text

def runs(headline: str) -> list[tuple[str, bool]]:
    """`Your reps **count** themselves` -> words tagged accent or not."""
    out = []
    for i, part in enumerate(re.split(r"\*\*", headline)):
        out += [(w, i % 2 == 1) for w in part.split()]
    return out


def wrap(draw: ImageDraw.ImageDraw, words: list, font, width: int) -> list[list]:
    lines, cur = [], []
    for word in words:
        trial = " ".join(w for w, _ in cur + [word])
        if cur and draw.textlength(trial, font=font) > width:
            lines.append(cur)
            cur = [word]
        else:
            cur.append(word)
    return lines + ([cur] if cur else [])


def draw_caption(canvas: Image.Image, shot: dict, style: Style, left: int, top: int, width: int,
                 scale: float, center_vertically_in: int | None = None) -> int:
    """Eyebrow, headline (accent run in **...**), subline. Returns the bottom y."""
    draw = ImageDraw.Draw(canvas)
    accent = hex_rgb(shot["accent"]) if shot.get("accent") else style.accent
    eyebrow_f = style.font("eyebrow", round(34 * scale))
    head_size = round((112 if len(shot.get("headline", "")) > 30 else 128) * scale)
    head_f = style.font("headline", head_size)
    sub_f = style.font("body", round(46 * scale))
    gap = round(28 * scale)
    head_lines = wrap(draw, runs(shot.get("headline", "")), head_f, width)
    sub_lines = wrap(draw, [(w, False) for w in shot.get("subline", "").split()], sub_f, width)
    heights = [round(34 * scale * 1.3) if shot.get("eyebrow") else 0, len(head_lines) * round(head_size * 1.05),
               len(sub_lines) * round(46 * scale * 1.3)]
    block = sum(heights) + gap * (sum(1 for h in heights if h) - 1)
    y = top if center_vertically_in is None else (center_vertically_in - block) // 2
    if shot.get("eyebrow"):
        draw.text((left, y), shot["eyebrow"].upper(), font=eyebrow_f, fill=accent)
        y += heights[0] + gap
    for line in head_lines:
        x = left
        for i, (word, is_accent) in enumerate(line):
            text = word + (" " if i < len(line) - 1 else "")
            draw.text((x, y), text, font=head_f, fill=accent if is_accent else style.text)
            x += draw.textlength(text, font=head_f)
        y += round(head_size * 1.05)
    if sub_lines:
        y += gap
    for line in sub_lines:
        draw.text((left, y), " ".join(w for w, _ in line), font=sub_f, fill=style.subline)
        y += round(46 * scale * 1.3)
    return y


# ---------------------------------------------------------------- frames

def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    f = 4  # drawn at 4x and downsampled, for smooth corners
    big = Image.new("L", (size[0] * f, size[1] * f), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, size[0] * f - 1, size[1] * f - 1), radius=radius * f, fill=255)
    return big.resize(size, Image.LANCZOS)


def draw_frame(canvas: Image.Image, raw: Image.Image, box: tuple[int, int, int, int], style: Style) -> None:
    """The screen cover-fit (top-anchored) inside a rounded frame at `box`."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    radius = round(min(w, h) * 0.13)
    pad = max(6, round(min(w, h) * 0.016))
    shadow = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + round(h * 0.02), x1, y1 + round(h * 0.02)),
                                             radius=radius, fill=120)
    canvas.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(max(8, round(w * 0.04)))))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(box, radius=radius, fill=style.frame, outline=style.ring, width=max(2, round(w * 0.003)))
    iw, ih = w - 2 * pad, h - 2 * pad
    fit = max(iw / raw.width, ih / raw.height)
    scaled = raw.resize((round(raw.width * fit), round(raw.height * fit)), Image.LANCZOS)
    off = max(0, (scaled.width - iw) // 2)
    canvas.paste(scaled.crop((off, 0, off + iw, ih)), (x0 + pad, y0 + pad), rounded_mask((iw, ih), radius - pad))


# ---------------------------------------------------------------- layouts

def compose_portrait(shot: dict, raw: Image.Image, size: tuple[int, int], style: Style) -> Image.Image:
    w, h = size
    canvas = Image.new("RGB", size, style.background)
    scale = w / 1320
    left, width = round(w * 0.083), round(w * 0.834)
    bottom = draw_caption(canvas, shot, style, left, round(h * 0.06), width, scale)
    frame_w = round(w * 0.76)
    frame_h = round(frame_w * raw.height / raw.width)
    top = max(bottom + round(h * 0.035), round(h * 0.25))
    x0 = (w - frame_w) // 2
    draw_frame(canvas, raw, (x0, top, x0 + frame_w, top + frame_h), style)  # bleeds off the bottom
    return canvas


def compose_side(shot: dict, raw: Image.Image, size: tuple[int, int], style: Style) -> Image.Image:
    w, h = size
    canvas = Image.new("RGB", size, style.background)
    # Box for the screen on the right; the frame keeps the raw's aspect.
    bx0, by0, bx1, by1 = round(w * 0.52), round(h * 0.07), round(w * 0.95), round(h * 0.93)
    fit = min((bx1 - bx0) / raw.width, (by1 - by0) / raw.height)
    fw, fh = round(raw.width * fit), round(raw.height * fit)
    fx0, fy0 = bx0 + ((bx1 - bx0) - fw) // 2, by0 + ((by1 - by0) - fh) // 2
    draw_frame(canvas, raw, (fx0, fy0, fx0 + fw, fy0 + fh), style)
    text_w = round(w * 0.42)
    draw_caption(canvas, shot, style, round(w * 0.06), 0, text_w, scale=text_w / 1100 * 1.1,
                 center_vertically_in=h)
    return canvas


LAYOUTS = {"portrait": compose_portrait, "side": compose_side}


def derive(base: Image.Image, width: int, height: int, background) -> Image.Image:
    """Scale the finished base canvas to `width`, then center-crop (or pad) to
    `height`: every slot shows the same composition."""
    scaled = base.resize((width, round(base.height * width / base.width)), Image.LANCZOS)
    if scaled.height <= height:
        out = Image.new("RGB", (width, height), background)
        out.paste(scaled, (0, (height - scaled.height) // 2))
        return out
    top = (scaled.height - height) // 2
    return scaled.crop((0, top, width, top + height))


# ---------------------------------------------------------------- main

def render_set(name: str, spec: dict, cfg: dict, base: Path, style: Style) -> list[Path]:
    layout = spec.get("layout", "portrait")
    slots = spec.get("slots") or cfg.get("slots")
    derive_slots = spec.get("derive", layout == "portrait")
    raw_dir = base / spec.get("raw_dir", cfg.get("raw_dir", "raw"))
    out_root = base / spec.get("out_dir", name)
    pattern = spec.get("file_pattern", cfg.get("file_pattern", "shot-{n:02d}.png"))
    written = []
    for _, _, slot_dir in slots:
        d = out_root / slot_dir
        d.mkdir(parents=True, exist_ok=True)
        for stale in d.glob("*.png"):
            stale.unlink()
    print(f"=== {name} ({layout}, {len(spec['shots'])} shots) ===")
    for n, shot in enumerate(spec["shots"], start=1):
        raw = load_raw(shot, raw_dir, style, strip_default=spec.get("strip_status_bar", layout == "portrait"))
        fname = shot.get("file") or pattern.format(n=n)
        first = None
        for i, (w, h, slot_dir) in enumerate(slots):
            if i and derive_slots:
                img = derive(first, w, h, style.background)
            else:
                img = LAYOUTS[layout](shot, raw, (w, h), style)
            first = first or img
            dst = out_root / slot_dir / fname
            img.convert("RGB").save(dst, "PNG", optimize=True)
            written.append(dst)
        print(f"  {fname} ← {shot['raw']}  \"{shot.get('headline', '').replace('**', '')}\"")
    return written


def verify(paths) -> int:
    bad = 0
    for p in sorted(paths):
        with Image.open(p) as im:
            expected = next((tuple(map(int, m.groups())) for m in [re.search(r"(\d+)x(\d+)", p.parent.name)] if m), None)
            problems = []
            if im.mode != "RGB":
                problems.append(f"mode {im.mode} (needs RGB, no alpha)")
            if expected and im.size != expected:
                problems.append(f"{im.size[0]}x{im.size[1]}, folder says {expected[0]}x{expected[1]}")
            print(f"  {'✗' if problems else '✔'} {p}  {im.size[0]}x{im.size[1]} {im.mode} {'; '.join(problems)}")
            bad += bool(problems)
    return bad


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config")
    p.add_argument("--set", action="append", help="render only these sets")
    p.add_argument("--verify", action="store_true", help="check the rendered files instead of rendering")
    args = p.parse_args()
    cfg_path = Path(args.config).resolve()
    cfg = json.loads(cfg_path.read_text())
    base = cfg_path.parent
    style = Style(cfg, base)
    names = args.set or list(cfg["sets"])
    if args.verify:
        paths = {f for n in names for f in (base / cfg["sets"][n].get("out_dir", n)).rglob("*.png")}
        sys.exit(1 if verify(paths) else 0)
    written = []
    for name in names:
        written += render_set(name, cfg["sets"][name], cfg, base, style)
    print(f"\n{len(written)} files. Check them with --verify, then look at every one before upload.")


if __name__ == "__main__":
    main()
