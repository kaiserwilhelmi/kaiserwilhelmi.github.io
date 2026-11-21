"""Crop small map pictures around each NPC from the TibiaMaps.io map data (github.com/tibiamaps/tibia-map-data).
Usage: python3 build_maps.py FLOOR_DIR   (FLOOR_DIR holds floor-NN.png, 1 px per tile)"""
import json, sys, os
from PIL import Image, ImageDraw
X0, Y0 = 31744, 30976          # bounds.json xMin / yMin
T, SCALE = 90, 3               # tiles shown each way, pixels per tile
fd = sys.argv[1]
d = json.load(open('data/items.json'))
floors = {}
def floor(z):
    if z not in floors: floors[z] = Image.open(os.path.join(fd, f'floor-{z:02d}.png')).convert('RGB')
    return floors[z]
os.makedirs('data/maps', exist_ok=True)
def crop(x, y, z, out):
    im = floor(z); px, py = x - X0, y - Y0
    c = im.crop((px - T // 2, py - T // 2, px + T // 2, py + T // 2)).resize((T * SCALE, T * SCALE), Image.NEAREST)
    dr = ImageDraw.Draw(c); cx = cy = T // 2 * SCALE + SCALE // 2
    for r, col, w in ((15, (0, 0, 0), 6), (15, (255, 214, 64), 3)):
        dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=w)
    dr.rectangle((cx - 2, cy - 2, cx + 2, cy + 2), fill=(255, 214, 64))
    c.save(out, optimize=True)
n = 0
for i, r in enumerate(d['npcs']):
    if r[3] is not None: crop(r[3], r[4], r[5], f'data/maps/n{i}.png'); n += 1
for i, r in enumerate(d['rashid_at']):
    crop(r[1], r[2], r[3], f'data/maps/r{i}.png'); n += 1
print(n, 'map pictures')
