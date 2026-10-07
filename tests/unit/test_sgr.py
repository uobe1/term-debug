#!/usr/bin/env python3
"""Unit tests for the SGR parser — sample bytes from the term_research phase."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from termdebug.screen import color_name, find_text, parse_grid, rows_to_runs


def cells(grid):
    return [c for row in grid for c in row if c is not None]


def test_basic_fg_and_reset():
    grid = parse_grid("\x1b[31mRED\x1b[0m ok")
    cs = cells(grid)
    assert [c["char"] for c in cs] == list("RED ok"), cs
    assert all(c["fg"] == "red" for c in cs[:3]), cs
    assert cs[3]["fg"] is None and cs[4]["fg"] is None, cs


def test_bold_underline_combo():
    grid = parse_grid("\x1b[1;4mB\x1b[0m")
    c = cells(grid)[0]
    assert c["attrs"] == ["bold", "underline"], c


def test_sgr_carries_across_lines():
    grid = parse_grid("\x1b[31mA\nB")
    rows = [[c for c in row if c] for row in grid]
    assert rows[0][0]["fg"] == "red"
    assert rows[1][0]["fg"] == "red", "SGR state must survive newline"


def test_256_and_truecolor_fg():
    grid = parse_grid("\x1b[38;5;196mX\x1b[0m\x1b[38;2;1;2;3mY")
    cs = cells(grid)
    assert cs[0]["fg"] == 196, cs[0]
    assert cs[1]["fg"] == "#010203", cs[1]


def test_bright_colors():
    assert color_name(1) == "red"
    assert color_name(9) == "bright-red"
    grid = parse_grid("\x1b[91mX")
    assert cells(grid)[0]["fg"] == "bright-red"


def test_non_sgr_csi_skipped():
    grid = parse_grid("\x1b[2DX")  # cursor-left is not styling; ignore
    c = cells(grid)[0]
    assert c["char"] == "X" and c["fg"] is None


def test_reverse_attr():
    grid = parse_grid("\x1b[7mX\x1b[27mY")
    cs = cells(grid)
    assert cs[0]["attrs"] == ["reverse"]
    assert cs[1]["attrs"] == []


def test_runs_merge_and_split():
    runs = rows_to_runs(parse_grid("\x1b[31mAB\x1b[0mCD"))[0]
    assert runs == [
        {"text": "AB", "fg": "red", "bg": None, "attrs": []},
        {"text": "CD", "fg": None, "bg": None, "attrs": []},
    ], runs


def test_cell_coordinates():
    grid = parse_grid("ab\ncd")
    cs = cells(grid)
    assert [(c["x"], c["y"]) for c in cs] == [(0, 0), (1, 0), (0, 1), (1, 1)], cs


def test_bg_colors():
    grid = parse_grid("\x1b[44mX\x1b[0m")
    assert cells(grid)[0]["bg"] == "blue"


def test_find_text_click_ready_coords():
    grid = parse_grid("MENU\n  [Cancel] [OK]")
    assert find_text(grid, "Cancel") == [{"text": "Cancel", "x": 4, "y": 2}]
    assert find_text(grid, "OK") == [{"text": "OK", "x": 13, "y": 2}]


def test_find_text_multiple_and_reading_order():
    grid = parse_grid("aXbX\nX")
    assert [m["x"] for m in find_text(grid, "X")] == [2, 4, 1]
    assert [m["y"] for m in find_text(grid, "X")] == [1, 1, 2]


def test_find_text_no_match_and_empty_needle():
    grid = parse_grid("hello")
    assert find_text(grid, "nope") == []
    assert find_text(grid, "") == [], "empty needle must not match every boundary"


def test_find_text_sgr_boundaries_do_not_break_match():
    # 'Cancel' painted with an SGR change INSIDE the word still matches:
    # the grid is character-based, escapes are not characters.
    grid = parse_grid("[Can\x1b[7mcel]")
    assert find_text(grid, "Cancel") == [{"text": "Cancel", "x": 2, "y": 1}]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all tests passed")
