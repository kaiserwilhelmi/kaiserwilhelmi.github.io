"""Build data/items.json from the TibiaWiki snapshot (@tibia.sh/tibiawiki-data, CC BY-SA 3.0).
Usage: python3 build_data.py path/to/index.db"""
import sqlite3, json, sys, re
from collections import defaultdict

db = sys.argv[1]
c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
info = dict(c.execute('select key,value from database_info'))
GOLD = c.execute("select article_id from item where title='Gold Coin'").fetchone()[0]

# Where each NPC stands: TibiaWiki location text and map coordinates
where = {t: ((loc or '').strip(), x, y, z) for t, loc, x, y, z in c.execute("select title,location,x,y,z from npc where status='active'")}
# NPCs that buy items from players, paid in gold
buy = defaultdict(list)
npcs, npc_idx = [], {}
for item_id, npc, city, val in c.execute(
        "select b.item_id,n.title,n.city,b.value from npc_offer_buy b join npc n on n.article_id=b.npc_id "
        "where b.currency_id=? and n.status='active' and b.value>0", (GOLD,)):
    if npc not in npc_idx:
        npc_idx[npc] = len(npcs); npcs.append([npc, city or ''] + list(where.get(npc, ('', None, None, None))))
    buy[item_id].append([npc_idx[npc], val])

sells = defaultdict(list)
for item_id, npc, city, val in c.execute(
        "select s.item_id,n.title,n.city,s.value from npc_offer_sell s join npc n on n.article_id=s.npc_id "
        "where s.currency_id=? and n.status='active' and s.value>0", (GOLD,)):
    if npc not in npc_idx:
        npc_idx[npc] = len(npcs); npcs.append([npc, city or ''] + list(where.get(npc, ('', None, None, None))))
    sells[item_id].append([npc_idx[npc], val])

imgs = {}
for aid, url in c.execute("select article_id,url from mcp_image where entity_type='item'"):
    m = re.match(r'https://static\.wikia\.nocookie\.net/tibia/images/(.+?)/revision/latest', url)
    if m: imgs[aid] = m.group(1)

drops = defaultdict(list); cre, cre_idx = [], {}
for item_id, name, chance, rarity, boss in c.execute(
        "select d.item_id,cr.title,d.chance,d.rarity,cr.is_boss from creature_drop d join creature cr "
        "on cr.article_id=d.creature_id where cr.status='active'"):
    drops[item_id].append((name, chance, rarity, boss))

RAR = {'always': 5, 'common': 4, 'uncommon': 3, 'semi-rare': 2, 'rare': 1, 'very rare': 0}
items = []
for (aid, title, plural, actual, mk, st, vsell, w, typ, note, status) in c.execute(
        "select article_id,title,plural,actual_name,is_marketable,is_stackable,value_sell,weight,item_type,"
        "trade_value_note,status from item where status in ('active','event') and is_pickupable=1"):
    b = sorted(buy.get(aid, []), key=lambda x: -x[1])
    q = sorted(sells.get(aid, []), key=lambda x: x[1])
    if not (mk or (vsell or 0) > 0 or b or q): continue
    if title == 'Gold Coin': continue
    d = drops.get(aid, [])
    # most likely droppers first (known chance desc, then rarity), max 8
    d.sort(key=lambda x: (-(x[1] or -1), -RAR.get(x[2], -1)))
    dd = []
    for name, chance, rarity, boss in d[:8]:
        if name not in cre_idx: cre_idx[name] = len(cre); cre.append(name)
        dd.append([cre_idx[name], round(chance, 3) if chance is not None else None, rarity or '', 1 if boss else 0])
    o = {'n': title}
    if plural and plural.lower() != title.lower() + 's': o['p'] = plural
    if actual and actual.lower() != title.lower(): o['a'] = actual
    if mk: o['m'] = 1
    if st: o['s'] = 1
    if vsell: o['v'] = vsell
    if w is not None: o['w'] = w
    if typ: o['t'] = typ
    if note: o['r'] = note
    if b: o['b'] = b
    if q: o['q'] = q
    if dd: o['d'] = dd
    if aid in imgs: o['i'] = imgs[aid]
    items.append(o)
items.sort(key=lambda o: o['n'].lower())

# Quests: TibiaWiki infobox fields (no walkthrough text in the snapshot; the app links to each wiki page)
quests = []
for (qid, title, loc, legend, lr, lrec, prem, qlog, typ, est, ver, rook) in c.execute(
        "select article_id,title,location,legend,level_required,level_recommended,is_premium,quest_log,type,"
        "estimated_time,version,is_rookgaard_quest from quest where status='active'"):
    q = {'n': title}
    if loc: q['l'] = loc.strip().rstrip('.')
    if legend: q['g'] = legend.strip()
    if lr: q['lr'] = lr
    if lrec: q['lc'] = lrec
    if prem: q['p'] = 1
    if qlog: q['ql'] = 1
    if typ: q['t'] = typ
    if est: q['e'] = est
    if rook: q['rk'] = 1
    rw = [r[0] for r in c.execute("select i.title from quest_reward r join item i on i.article_id=r.item_id where r.quest_id=?", (qid,))]
    if rw: q['r'] = rw
    dg = [r[0] for r in c.execute("select cr.title from quest_danger d join creature cr on cr.article_id=d.creature_id where d.quest_id=?", (qid,))]
    if dg: q['d'] = dg[:15]
    of = sorted({o + (' addons' if u == 'addons' else '') for o, u in c.execute(
        "select o.title,oq.unlock_type from outfit_quest oq join outfit o on o.article_id=oq.outfit_id where oq.quest_id=?", (qid,))})
    if of: q['o'] = of
    quests.append(q)
quests.sort(key=lambda q: q['n'].lower())

rashid = [r[0] for r in c.execute('select city from rashid_position order by day')]
travel = defaultdict(list)  # destination city -> [captain, from city, price, note]
for cap, frm, dest, price, note in c.execute(
        "select n.title,coalesce(d.origin,n.city),d.name,d.price,d.notes from npc_destination d join npc n on n.article_id=d.npc_id where n.status='active'"):
    travel[dest].append([cap, frm or '', price, note or ''])
for v in travel.values(): v.sort(key=lambda r: r[2])
rashid_at = [list(r) for r in c.execute('select location,x,y,z from rashid_position order by day')]
worlds = sorted(r[0] for r in c.execute(
    "select title from world where offline_since is null and is_preview=0 and is_experimental=0"))
out = {'source': 'TibiaWiki (tibia.fandom.com) via @tibia.sh/tibiawiki-data, CC BY-SA 3.0',
       'generated': info.get('generate_time'), 'npcs': npcs, 'creatures': cre,
       'rashid': rashid, 'rashid_at': rashid_at, 'travel': travel, 'quests': quests, 'worlds': worlds, 'items': items}
json.dump(out, open('data/items.json', 'w'), separators=(',', ':'))
print(len(quests), 'quests', len(items), 'items', len(npcs), 'npcs', len(cre), 'creatures', len(worlds), 'worlds')
