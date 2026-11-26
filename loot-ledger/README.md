# Loot Ledger (Tibia loot companion)

A personal web app for deciding where to sell Tibia loot and keeping track of good drops.

## What it does
- **Lookup** (opens first): type an item to see every NPC that buys it (best price first, with city; Rashid's city for today), who sells it, TibiaWiki trade estimate, weight and top droppers. Tap an NPC (or type its name) to see everything it buys and sells plus a "How to find" guide (quest notes like "Blue Djinn access" open that quest in the Quests tab): boats to its city, the exact spot, floor, quest access, and a small map with the NPC ringed, plus a link to the full TibiaMaps.io map. Rashid's guide shows his weekly route with today highlighted.
- **Quests**: all 369 active TibiaWiki quests with level required/recommended, premium, location, summary, rewards, outfit unlocks and creatures faced. She sets each to Not started / In progress / Done and adds her own step checklist. Filter by her level (pulled from TibiaData when hosted). Full walkthroughs link to each quest's TibiaWiki page, because the snapshot holds the quest infobox, not the walkthrough text.
- **Hunts**: after pricing loot in Sell, "Save this hunt" stores it. Session time, XP, supplies and kills are read from the Hunt Analyser text; the hunting place is an optional box. The tab shows hunts saved, hoard so far, profit per hour, the best hunt, and a table of hunting places ranked by profit per hour.
- **Sell**: paste Hunt Analyser text, Server Log loot messages, or a plain item list. Each item gets the best NPC (with city; Rashid's city for today), your latest logged market prices, the TibiaWiki trade estimate, gp per oz, and a call: NPC, Market now, List on market, or Check market. NPC sales are grouped into a route.
- **Prices**: optional market price log per world (there is no public market feed). Buy and sell offers over time, chart, and a NPC price reference line.
- **Trophies**: rare drop log with creature, date, kill count and value.
- **Wishlist**: items she's chasing, who drops them (TibiaWiki chances), and a flag when a logged sell offer is under her target.
- **Setup**: character and world (character info from TibiaData when reachable), market fee, backup and restore.

Data is saved in the browser (localStorage). Use Setup → Backup to keep a copy. First run loads a few entries marked "example"; Setup → Remove example entries clears them.

## The look and the dragon
The page is styled like an early-2000s game window: a stone wall, grey stone frames with beveled edges, a parchment strip for today's news and pixel lettering (Pixelify Sans, SIL Open Font License 1.1). It does not use the site's night-sky theme; that was Dawson's choice for this page only. A bar at the top links back to the site.

On the first visit in a browser session a dragon comes out of the dark, opens its mouth and the page appears from its throat (about 3 seconds). Any click, tap or key skips it. It does not play when the device is set to reduce motion. "Meet the dragon again" at the bottom of the page replays it.

All of the art is original and drawn in code in `template.html`: the dragon on a small canvas that is cut to the 216 web-safe colors with an ordered dither and scaled up with hard pixels, the stone as two small generated tiles. No CipSoft artwork or sprites are used.

## Extras for playing
A second, separate script at the bottom of `template.html` adds small helpers. It only reads what the page has drawn and keeps its own store (`lootLedger.extras.v1`); it does not touch a price or a total.
- **Server save countdown** in the today strip (10:00 Berlin time, when Rashid moves).
- **Recent lookups** under the search box, and `/` jumps to the search from any tab.
- **Filter box** on an NPC's list when it has 13 or more items (Rashid buys 187).
- **Sold here** tick box on each stop of the NPC route, with a count of stops done. It resets when the loot text changes.

On a phone the Sell list shows one block per item instead of a wide table, and all seven tabs fit in two rows.

## Files
- `dist/index.html` + `dist/data/items.json`: hosted version (GitHub Pages or any static host).
- `dist/loot-ledger.html`: single file with the data built in; opens straight from disk.
- `template.html`: page source. `build.py` builds `dist/`.
- `build_data.py`: builds `data/items.json` from the TibiaWiki snapshot.

## Rebuild the data
```
npm pack @tibia.sh/tibiawiki-data
tar xzf tibia.sh-tibiawiki-data-*.tgz
python3 build_data.py package/index.db
python3 build.py
```

## Notes on the numbers
- NPC price = highest price any active NPC pays in gold coins (TibiaWiki `Module:ItemPrices` data). Rashid and the djinns need quest access; when the best buyer needs a quest, the best buyer that doesn't is shown too.
- Market now = your latest logged buy offer (no fee when you accept a buy offer). List on market = latest sell offer minus the fee set in Setup (default 2%; check in game).
- Lowball warning: shown when TibiaWiki's low estimate is at least 1,000 gp and twice the best NPC price, or the wiki lists the price as negotiable (rare items such as Dragon Scale Legs, which only H.L. buys, for 180 gp).
- Check market = no logged price, and TibiaWiki's low estimate is at least 1,000 gp and 20% above the NPC price.
- Hunts: loot = the "Following this plan" total on the day the hunt was saved (it is not re-priced later). Profit = loot minus supplies. Profit per hour and XP per hour = total divided by total time over the hunts that have a time, so long hunts count for more than short ones.
- Rashid's day turns over at server save, 10:00 Berlin time.

## Sources and credits
- Item, NPC (buy and sell offers, locations, coordinates, boat routes), creature drop, quest and Rashid data: TibiaWiki (https://tibia.fandom.com) and its contributors, CC BY-SA 3.0, via the @tibia.sh/tibiawiki-data snapshot generated 2026-11-20. `data/items.json` is an adaptation under the same licence.
- NPC map pictures (`data/maps/`): cropped from the TibiaMaps.io map data (https://github.com/tibiamaps/tibia-map-data), whose README invites reuse in other projects. Rebuild with `python3 build_maps.py <folder with floor-NN.png>`.
- Item images load from TibiaWiki's image host; they are not copied here.
- Boosted creature, boosted boss and character info: TibiaData API (https://tibiadata.com), fetched live when available.
- Tibia is © CipSoft GmbH. Fan-made; it does not read or automate the game client.

## What is automatic and what isn't
- Automatic: NPC buy/sell prices and cities, Rashid's city, quest info, drops, TibiaWiki market estimates; boosted creature/boss and character level once hosted.
- Manual: live player market prices. CipSoft publishes no market API and no reliable per-world community feed was found, so that log stays optional.
