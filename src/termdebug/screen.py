"""Text observation: SGR-aware cell grid, attribute runs, attribute grep.

Input is `tmux capture-pane -e -p` output (re-synthesized escape sequences).
The SGR state machine treats the stream as characters: `\n` moves rows, SGR
state carries across lines until explicitly reset. fg/bg come out as color
names for 0-15, ints for 256-palette, #rrggbb for truecolor.
"""
import re

NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")

CSI = re.compile(r"\x1b\[([0-9;:]*)([A-Za-z])")


def color_name(n: int) -> str | int:
    if 0 <= n <= 7:
        return NAMES[n]
    if 8 <= n <= 15:
        return "bright-" + NAMES[n - 8]
    return n  # 256-palette index


def truecolor(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _apply_sgr(params: str, st: dict) -> None:
    nums = [int(p) for p in params.replace(":", ";").split(";") if p] or [0]
    k = 0
    while k < len(nums):
        n = nums[k]
        if n == 0:
            st.update(fg=None, bg=None, attrs=set())
        elif n == 1:
            st["attrs"].add("bold")
        elif n == 2:
            st["attrs"].add("dim")
        elif n == 3:
            st["attrs"].add("italic")
        elif n == 4:
            st["attrs"].add("underline")
        elif n == 5:
            st["attrs"].add("blink")
        elif n == 7:
            st["attrs"].add("reverse")
        elif n == 9:
            st["attrs"].add("strikethrough")
        elif n == 22:
            st["attrs"].difference_update(("bold", "dim"))
        elif n == 23:
            st["attrs"].discard("italic")
        elif n == 24:
            st["attrs"].discard("underline")
        elif n == 27:
            st["attrs"].discard("reverse")
        elif n == 29:
            st["attrs"].discard("strikethrough")
        elif 30 <= n <= 37:
            st["fg"] = color_name(n - 30)
        elif n == 38:
            if k + 1 < len(nums) and nums[k + 1] == 5:
                st["fg"] = nums[k + 2] if k + 2 < len(nums) else None
                k += 2
            elif k + 1 < len(nums) and nums[k + 1] == 2:
                if k + 4 < len(nums):
                    st["fg"] = truecolor(tuple(nums[k + 2:k + 5]))
                k += 4
        elif n == 39:
            st["fg"] = None
        elif 40 <= n <= 47:
            st["bg"] = color_name(n - 40)
        elif n == 48:
            if k + 1 < len(nums) and nums[k + 1] == 5:
                st["bg"] = nums[k + 2] if k + 2 < len(nums) else None
                k += 2
            elif k + 1 < len(nums) and nums[k + 1] == 2:
                if k + 4 < len(nums):
                    st["bg"] = truecolor(tuple(nums[k + 2:k + 5]))
                k += 4
        elif n == 49:
            st["bg"] = None
        elif 90 <= n <= 97:
            st["fg"] = color_name(n - 90 + 8)
        elif 100 <= n <= 107:
            st["bg"] = color_name(n - 100 + 8)
        k += 1


def parse_grid(text: str) -> list[list[dict | None]]:
    """SGR byte stream -> sparse cell grid; None marks untouched slots."""
    st = {"fg": None, "bg": None, "attrs": set()}
    grid: list[list[dict | None]] = [[]]
    row = col = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\x1b":
            m = CSI.match(text, i)
            if m:
                if m.group(2) == "m":
                    _apply_sgr(m.group(1), st)
                i = m.end()
            else:
                i += 1  # lone ESC or non-CSI escape: ignore
            continue
        if ch == "\n":
            row += 1
            col = 0
            while row >= len(grid):
                grid.append([])
            i += 1
            continue
        if ch == "\r":
            col = 0
            i += 1
            continue
        line = grid[row]
        while len(line) <= col:
            line.append(None)
        line[col] = {"char": ch, "fg": st["fg"], "bg": st["bg"],
                     "attrs": sorted(st["attrs"]), "x": col, "y": row}
        col += 1
        i += 1
    return grid


def rows_to_runs(grid: list[list[dict | None]]) -> list[list[dict]]:
    """Merge adjacent same-attribute cells (None = plain space) into runs."""
    out = []
    for row in grid:
        runs: list[dict] = []
        for cell in row:
            if cell is None:
                ch, fg, bg, attrs = " ", None, None, []
            else:
                ch, fg, bg, attrs = cell["char"], cell["fg"], cell["bg"], cell["attrs"]
            if runs and runs[-1]["fg"] == fg and runs[-1]["bg"] == bg \
                    and runs[-1]["attrs"] == attrs:
                runs[-1]["text"] += ch
            else:
                runs.append({"text": ch, "fg": fg, "bg": bg, "attrs": list(attrs)})
        out.append(runs)
    return out


def grid_row_text(row: list[dict | None]) -> str:
    return "".join((c["char"] if c else " ") for c in row).rstrip()


def row_matches(row: list[dict | None], fg=None, bg=None, attrs=()) -> bool:
    return any(
        c is not None
        and (fg is None or c["fg"] == fg)
        and (bg is None or c["bg"] == bg)
        and all(a in c["attrs"] for a in attrs)
        for c in row
    )


def cell_at(grid: list[list[dict | None]], x: int, y: int) -> dict:
    """Screen-coordinate cell lookup; untouched slots look like plain spaces."""
    if 0 <= y < len(grid) and 0 <= x < len(grid[y]) and grid[y][x] is not None:
        return grid[y][x]
    return {"char": " ", "fg": None, "bg": None, "attrs": [], "x": x, "y": y}
