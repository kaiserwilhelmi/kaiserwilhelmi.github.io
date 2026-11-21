const { chromium } = require('playwright'); const fs = require('fs');
const page = require('path').resolve(__dirname, '../index.html'), dir = require('path').resolve(__dirname, 'uploads');
(async () => { const b = await chromium.launch(); 
 for (const f of fs.readdirSync(dir).sort()) { const p = await b.newPage(); const errs=[]; p.on('pageerror', e => errs.push(e.message));
  await p.goto('file://' + page); await p.waitForTimeout(300);
  await p.setInputFiles('#file', dir + '/' + f); await p.waitForTimeout(2500);
  const err = await p.$eval('#err', e => e.hidden ? '' : e.innerText);
  const note = await p.$eval('#upnote', e => e.innerText).catch(()=>'');
  const kp = await p.$eval('#kpis', e => e.innerText.replace(/\n/g,' | ').slice(0,90));
  const sel = await p.$eval('#series', e => e.options[e.selectedIndex].text);
  const m = await p.$eval('#m', e => e.value);
  console.log(f.padEnd(26), err ? 'ERROR: ' + err : 'OK series=' + sel + ' m=' + m + ' | ' + note + ' | ' + kp, errs.length ? errs : '');
  await p.close(); }
 await b.close(); })();
