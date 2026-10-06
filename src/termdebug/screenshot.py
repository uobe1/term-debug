"""Image channel: render the SGR cell grid to PNG/JPG via Pillow.

The terminal is the ground truth (capture-pane -e text), so the picture is
an exact re-synthesis: per-cell foreground/background from the grid, reverse
swapped, bold lifting 0-7 colors to their bright variants, xterm 256-palette
mapping for numeric colors, truecolor passed through.
"""
import glob
import os


# xterm-style base 16 palette (0-15)
BASE16 = (
    (0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
    (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229),
    (127, 127, 127), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
)
NAMES16 = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")

FG_DEFAULT = (229, 229, 229)
BG_DEFAULT = (0, 0, 0)

FONT_SIZE = 16


def find_font() -> str | None:
    """Probing order: DroidSansMono, any /system mono, $PREFIX share mono."""
    cands = glob.glob("/system/fonts/DroidSansMono*.ttf")
    cands += [p for p in glob.glob("/system/fonts/*.ttf") if "mono" in p.lower()]
    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    cands += [p for p in glob.glob(f"{prefix}/share/fonts/**/*.ttf", recursive=True)
              if "mono" in p.lower()]
    return cands[0] if cands else None


def pixel(color) -> tuple | None:
    """Color value (name | int | #hex) -> RGB tuple; None stays None."""
    if color is None:
        return None
    if isinstance(color, int):
        return _palette256(color)
    if color.startswith("#") and len(color) == 7:
        return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    bright = False
    name = color
    if color.startswith("bright-"):
        bright, name = True, color[len("bright-"):]
    if name in NAMES16:
        return BASE16[NAMES16.index(name) + (8 if bright else 0)]
    return None


def _palette256(n: int) -> tuple:
    if n < 16:
        return BASE16[n]
    if n < 232:  # 6x6x6 color cube
        n -= 16
        lv = (0, 95, 135, 175, 215, 255)
        return (lv[n // 36], lv[(n // 6) % 6], lv[n % 6])
    g = 8 + (n - 232) * 10  # grayscale ramp
    return (g, g, g)


def render(grid: list, out_path: str, fmt: str) -> dict:
    """Draw the grid; returns size/font info. Raises ImportError without Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    font_path = find_font()
    if font_path is None:
        raise FileNotFoundError("no monospace TTF found")
    font = ImageFont.truetype(font_path, FONT_SIZE)
    charw = max(1, round(font.getlength("M")))
    ascent, descent = font.getmetrics()
    lineh = ascent + descent
    height = len(grid)
    width = max((len(r) for r in grid), default=0)
    img = Image.new("RGB", (width * charw, height * lineh), BG_DEFAULT)
    draw = ImageDraw.Draw(img)
    for row in grid:
        for cell in row:
            if cell is None:
                continue
            fg = pixel(cell["fg"]) or FG_DEFAULT
            bg = pixel(cell["bg"]) or BG_DEFAULT
            attrs = cell.get("attrs") or []
            if "reverse" in attrs:
                fg, bg = bg, fg
            elif "bold" in attrs and isinstance(cell["fg"], str) \
                    and cell["fg"] in NAMES16:
                fg = BASE16[NAMES16.index(cell["fg"]) + 8]
            x0, y0 = cell["x"] * charw, cell["y"] * lineh
            draw.rectangle([x0, y0, x0 + charw - 1, y0 + lineh - 1], fill=bg)
            draw.text((x0, y0), cell["char"], font=font, fill=fg)
    if fmt == "jpg":
        img.save(out_path, "JPEG", quality=92)
    else:
        img.save(out_path, "PNG")
    return {"path": out_path, "size": [width * charw, height * lineh],
            "grid": [width, height], "charw": charw, "lineh": lineh,
            "font": os.path.basename(font_path)}
