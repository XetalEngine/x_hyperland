#!/usr/bin/env python3
"""Build the optional Hyper Fusion GRUB theme from repository assets."""

from pathlib import Path
import json
import subprocess

from PIL import Image, ImageDraw, ImageEnhance, ImageFont


ROOT = Path(__file__).resolve().parents[3]
THEME = Path(__file__).resolve().parent / "hyper-fusion"
SOURCE = ROOT / "config/hypr/wallpaper/modern/workstation-1.png"
PALETTES = ROOT / "config/hypr/theme/palettes.json"
FONTS = ROOT / "config/hypr/assets/fonts"
SIZE = (1920, 1080)


def color(value):
    return tuple(bytes.fromhex(value.lstrip("#")))


def background(palette):
    art = Image.open(SOURCE).convert("RGB")
    scale = max(SIZE[0] / art.width, SIZE[1] / art.height)
    art = art.resize((round(art.width * scale), round(art.height * scale)), Image.Resampling.LANCZOS)
    x = (art.width - SIZE[0]) // 2
    y = (art.height - SIZE[1]) // 2
    art = art.crop((x, y, x + SIZE[0], y + SIZE[1]))
    art = ImageEnhance.Brightness(art).enhance(0.72).convert("RGBA")

    # Opaque enough for the menu to stay legible across every part of the artwork.
    overlay = Image.new("RGBA", SIZE)
    pixels = overlay.load()
    base = color(palette["Base"])
    for px in range(SIZE[0]):
        alpha = round(238 - 174 * min(1, max(0, (px - 570) / 700)))
        for py in range(SIZE[1]):
            pixels[px, py] = (*base, alpha)
    art = Image.alpha_composite(art, overlay)
    draw = ImageDraw.Draw(art)
    accent = color(palette["Accent"])
    draw.rounded_rectangle((111, 210, 117, 291), radius=3, fill=(*accent, 255))
    draw.line((112, 884, 790, 884), fill=(*accent, 90), width=2)
    art.convert("RGB").save(THEME / "background.png", optimize=True)


def selection(palette):
    # The nine files form one scalable, rounded selection row in GRUB.
    canvas = Image.new("RGBA", (48, 48))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, 47, 47), radius=12, fill=(*color(palette["Highlight"]), 240))
    draw.rounded_rectangle((0, 0, 47, 47), radius=12, outline=(*color(palette["Accent"]), 255), width=2)
    cuts = (0, 16, 32, 48)
    for row, vertical in enumerate(("n", "", "s")):
        for col, horizontal in enumerate(("w", "", "e")):
            name = vertical + horizontal or "c"
            canvas.crop((cuts[col], cuts[row], cuts[col + 1], cuts[row + 1])).save(
                THEME / f"select_{name}.png", optimize=True
            )


def font(source, name, size, destination):
    subprocess.run(
        ["grub-mkfont", "--name", name, "--size", str(size),
         "--output", str(THEME / destination), str(FONTS / source)],
        check=True,
    )


def preview(palette):
    """Render a visual guide; actual GRUB text is laid out by theme.txt."""
    canvas = Image.open(THEME / "background.png").convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    heading = ImageFont.truetype(FONTS / "Inter-Bold.otf", 44)
    detail = ImageFont.truetype(FONTS / "Inter-Medium.otf", 17)
    menu = ImageFont.truetype(FONTS / "Inter-Regular.otf", 22)
    selected = ImageFont.truetype(FONTS / "Inter-SemiBold.otf", 22)
    draw.text((134, 218), "HYPER FUSION", font=heading, fill=palette["WindowText"])
    draw.text((134, 303), "Choose a system to start", font=detail, fill=palette["PlaceholderText"])
    entries = ("Arch Linux", "Advanced options for Arch Linux", "UEFI Firmware Settings")
    for index, entry in enumerate(entries):
        top = 389 + index * 56
        if index == 0:
            draw.rounded_rectangle((134, top, 958, top + 48), radius=12,
                                   fill=palette["Highlight"], outline=palette["Accent"], width=2)
        draw.text((150, top + 10), entry, font=selected if index == 0 else menu,
                  fill=palette["HighlightedText"] if index == 0 else palette["Text"])
    draw.text((134, 895), "Use arrow keys to select an entry. Press Enter to boot.",
              font=detail, fill=palette["PlaceholderText"])
    draw.text((134, 970), "Booting in 5 seconds", font=detail, fill=palette["Accent"])
    canvas.convert("RGB").save(THEME.parent / "preview.png", optimize=True)


def main():
    THEME.mkdir(parents=True, exist_ok=True)
    palette = json.loads(PALETTES.read_text())["modern"]["dark"]
    background(palette)
    selection(palette)
    font("Inter-Regular.otf", "Fusion Menu", 22, "menu.pf2")
    font("Inter-SemiBold.otf", "Fusion Selected", 22, "selected.pf2")
    font("Inter-Bold.otf", "Fusion Heading", 44, "heading.pf2")
    font("Inter-Medium.otf", "Fusion Detail", 17, "detail.pf2")
    preview(palette)
    print(THEME)


if __name__ == "__main__":
    main()
