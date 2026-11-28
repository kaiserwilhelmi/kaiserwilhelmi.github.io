# dawsonwilhelmi.com

Source for my portfolio site of purchasing and supply chain tools, served by GitHub Pages.

- `index.html` (Projects) and `about/index.html` (About): one page with two views, both built from `home/template.html` by `home/build.py` (see the note at the top of that file). Edit the About text in the template, not in `about/index.html`. `space.js`: the Earth graphic both pages share, built from `home/space.src.js` by the same script. `404.html`: the page shown for a wrong address.
- `forecast-compare/`: Forecast Method Comparison (its README covers the build and tests).
- `loot-ledger/`: Loot Ledger, a side project for the game Tibia.
- `theme.css`, `theme.js`: the site theme every page loads (see Theme below).
- `fonts/`: the site's fonts, served from here instead of Google Fonts.
- `tools/check_theme.py`: checks that every page is on the theme.
- Industry Market Watch and Supplier Scorecard live in their own repositories and are served at `/market-watch/` and `/supplier-scorecard/`.

## Theme

Every page on the site uses one shared look, set in two files at the root of this repo: `theme.css` (colors, fonts, the site header, the skip link) and `theme.js` (the stars behind the top of the page). Market Watch and the Scorecard live in their own repos but load the same two files by absolute path.

- Each page loads `/fonts/fonts.css`, then `/theme.css` before its own styles, and `/theme.js` at the end.
- Each page uses the shared header markup (`<header class="dw-site">`) and skip link (`class="dw-skip"`).
- A page takes every color and font from a theme token with a fallback, for example `--bg: var(--ink, #080c15);`.
- `theme.js` also plays a small effect on some pages as they open (the meteor and cost map on Projects, the coordinates on About, the satellite on the 404 page, the Market Watch cards and sparklines, the M5 rank). Each one picks its page by address or by an element only that page has, is skipped for visitors who ask for reduced motion, and leaves every word and number as the page wrote it. Their styles sit at the end of `theme.css`.
- To change the look of the whole site, edit `theme.css` only. `404.html` is the smallest page on the theme; start a new page from it.
- `tools/check_theme.py` checks every page against these rules and runs on each pull request (`.github/workflows/theme-check.yml`).

## Rights

© 2026 Dawson Wilhelmi. All rights reserved. The code is public so it can be read; it is not licensed for reuse. Data belongs to its publishers and is used under their terms, credited on each page. The Loot Ledger item data comes from TibiaWiki under CC BY-SA 3.0. The fonts in `fonts/` are under the SIL Open Font License (`fonts/OFL.txt`).
