"""Build the hosted page (dist/index.html + dist/data/items.json) and a single-file copy (dist/loot-ledger.html)."""
import json, shutil, os, sys
OUT = sys.argv[1] if len(sys.argv) > 1 else "dist"   # e.g. python3 build.py .  (inside the site repo)
src = open('template.html', encoding='utf-8').read()
head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')
title_end = src.index('</style>') + len('</style>')
page = lambda body_extra: head + src[:title_end] + '\n</head>\n<body>\n' + src[title_end:].replace('<!--DATA-->', body_extra) + '\n</body>\n</html>\n'
os.makedirs(os.path.join(OUT,'data'), exist_ok=True)
if os.path.abspath(OUT) != os.path.abspath('.'): shutil.copy('data/items.json', os.path.join(OUT,'data/items.json'))
import base64, glob
maps = {os.path.basename(f)[:-4]: 'data:image/png;base64,' + base64.b64encode(open(f, 'rb').read()).decode() for f in glob.glob('data/maps/*.png')}
if maps: json.dump(maps, open('data/maps.json', 'w'), separators=(',', ':'))  # rebuilt only when build_maps.py output is present
else: maps = json.load(open('data/maps.json'))
if os.path.abspath(OUT) != os.path.abspath('.'): shutil.copy('data/maps.json', os.path.join(OUT,'data/maps.json'))
# hosted page only: a bar that links back to the site, a skip link, and the pixel font served from this site.
# This page keeps its own early-2000s game look and does not load the site theme (/theme.css, /theme.js); the single-file copy
# has no site bar and keeps Google Fonts.
FONTS = '<link rel="stylesheet" href="/fonts/loot-ledger.css">'
SKIP = '<a class="dw-skip" href="#main">Skip to content</a>'
SITE = '<header class="dw-site">\n  <a class="dw-me" href="/">Dawson Wilhelmi</a>\n  <nav aria-label="Site"><a href="/">Projects</a><a href="/about/">About</a></nav>\n</header>'
hosted = page('')
GOOGLE = hosted[hosted.index('<link rel="preconnect" href="https://fonts.googleapis.com">'):hosted.index('display=swap">') + len('display=swap">')]
hosted = hosted.replace(GOOGLE, FONTS, 1)
hosted = hosted.replace('<div class="wrap">\n<main', SKIP + '\n<div class="wrap">\n' + SITE + '\n<main', 1)
assert SITE in hosted and FONTS in hosted and SKIP in hosted
open(os.path.join(OUT,'index.html'), 'w', encoding='utf-8').write(hosted)
if OUT == 'dist':
  data = open('data/items.json', encoding='utf-8').read().replace('</', '<\\/')
  open(os.path.join(OUT,'loot-ledger.html'), 'w', encoding='utf-8').write(page('<script>window.LOOT_DATA=' + data + ';window.LOOT_MAPS=' + json.dumps(maps) + ';</script>'))
print('built', OUT)
