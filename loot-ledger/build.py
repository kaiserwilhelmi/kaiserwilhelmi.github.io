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
HOME = '<nav class="home" style="padding-top:14px"><a href="/" style="font-weight:700;font-size:15px;color:var(--fg);text-decoration:none">Dawson Wilhelmi</a></nav>\n'
open(os.path.join(OUT,'index.html'), 'w', encoding='utf-8').write(page('').replace('<header class="top">', HOME + '<header class="top">', 1))
if OUT == 'dist':
  data = open('data/items.json', encoding='utf-8').read().replace('</', '<\\/')
  open(os.path.join(OUT,'loot-ledger.html'), 'w', encoding='utf-8').write(page('<script>window.LOOT_DATA=' + data + ';window.LOOT_MAPS=' + json.dumps(maps) + ';</script>'))
print('built', OUT)
