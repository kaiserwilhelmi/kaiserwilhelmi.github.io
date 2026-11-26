"""Check that every page in this repo is on the site theme (/theme.css + /theme.js).

Each page must:
  - link /theme.css (a ?v= stamp is fine) and load /theme.js,
  - carry the shared header (class "dw-site") and the skip link (class "dw-skip"),
  - contain none of the colors and fonts the site used before the theme.

Usage: python3 tools/check_theme.py   (exit code 1 lists every problem)
The same rules run in the market-watch and supplier-scorecard repos as part of their tests.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = ("forecast-compare/research", "forecast-compare/test/", "dist/", "node_modules/", "tools/")
# loot-ledger/template.html is not a page: build.py adds the header, the theme and the skip link to it.
SKIP_FILES = {"loot-ledger/template.html"}
RETIRED = ["#161a1f", "#1b2026", "#303741", "#262c34", "#ebe8e1", "#aeb3b9", "#8f969f", "#9cc0dc", "156,192,220",
           "Source Serif"]


def problems(text):
    """Every way one page breaks the theme rule, as short sentences (empty when it follows it)."""
    out = []
    if not re.search(r'<link rel="stylesheet" href="/theme\.css(\?v=[0-9a-f]+)?">', text):
        out.append("does not link /theme.css")
    if not re.search(r'<script src="/theme\.js(\?v=[0-9a-f]+)?"( defer)?></script>', text):
        out.append("does not load /theme.js")
    if not re.search(r'<header class="[^"]*\bdw-site\b', text):
        out.append('has no <header class="dw-site">')
    if 'class="dw-skip"' not in text:
        out.append("has no skip link (class dw-skip)")
    low = text.lower().replace(" ", "")
    for v in RETIRED:
        if v.lower().replace(" ", "") in low:
            out.append(f"still uses the retired value {v}")
    return out


def main():
    bad = 0
    pages = sorted(p for p in ROOT.rglob("*.html")
                   if not any(s in p.relative_to(ROOT).as_posix() for s in SKIP_DIRS)
                   and p.relative_to(ROOT).as_posix() not in SKIP_FILES
                   and ".git/" not in p.as_posix())
    for p in pages:
        for msg in problems(p.read_text(encoding="utf-8")):
            print(f"{p.relative_to(ROOT)}: {msg}")
            bad += 1
    print(f"{len(pages)} pages checked, {bad} problem{'s' if bad != 1 else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
