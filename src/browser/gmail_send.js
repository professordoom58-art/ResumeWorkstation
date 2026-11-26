const fs = require('fs');
const path = require('path');
const L = require('./lib');

// Usage: node gmail_send.js <manifest.json>   (or M=<manifest.json> node gmail_send.js)
// manifest: [{id, to, subject, file (body .txt, relative to repo root), attach (pdf, relative to repo root)}]
// Every send is recorded in outbox/sent_all.json, the shared duplicate guard. An id or address already SENT is skipped.
const ROOT = path.resolve(__dirname, '..', '..');
const MANF = process.argv[2] || process.env.M;
if (!MANF) { console.error('usage: node gmail_send.js <manifest.json>'); process.exit(2); }
const MAN = JSON.parse(fs.readFileSync(path.resolve(MANF), 'utf8'));
// Resolved from the repo root, never the cwd: an empty guard is what caused the 23 Nov duplicates.
const SENTF = path.join(ROOT, 'outbox', 'sent_all.json');
if (!fs.existsSync(SENTF)) { console.error('ABORT: duplicate guard missing at ' + SENTF); process.exit(2); }
let sent = JSON.parse(fs.readFileSync(SENTF, 'utf8'));
const SHOTS = path.join(__dirname, 'shots'); fs.mkdirSync(SHOTS, { recursive: true });
const sentAddrs = new Set(Object.values(sent).filter(v => v.result === 'SENT').map(v => String(v.to || '').toLowerCase()).filter(Boolean));
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const rand = (a, b) => a + Math.floor(Math.random() * (b - a));

async function openCompose(page) {
  for (let i = 0; i < 4; i++) {
    try {
      const btn = page.locator('div[role="button"]').filter({ hasText: /^Compose$/ }).first();
      if (await btn.count()) { await btn.click({ timeout: 15000 }); }
      else { await page.getByRole('button', { name: /^compose$/i }).first().click({ timeout: 15000 }); }
      await page.waitForTimeout(2500);
      if (await page.$('div[aria-label="Message Body"]')) return true;
    } catch (e) { await page.waitForTimeout(1500); }
  }
  return false;
}

async function setTo(page, addr) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const el = await page.$('input[aria-label="To recipients"]') || await page.$('input[name="to"]');
    if (!el) return 'NOFIELD';
    await el.click({ timeout: 10000 }).catch(() => {});
    await page.keyboard.press('Control+A');
    await page.keyboard.press('Backspace');
    await page.waitForTimeout(300);
    await page.keyboard.insertText(addr);
    await page.waitForTimeout(1200);
    const val = await page.evaluate(() => {
      const i = document.querySelector('input[aria-label="To recipients"]') || document.querySelector('input[name="to"]');
      return i ? i.value.trim() : 'NOFIELD';
    });
    if (val.toLowerCase() === addr.toLowerCase()) {
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1600);
      const state = await page.evaluate(() => {
        const i = document.querySelector('input[aria-label="To recipients"]') || document.querySelector('input[name="to"]');
        const t = document.body.innerText;
        return { val: i ? i.value.trim() : 'NOFIELD',
                 bad: /address wasn.t found|isn.t a valid|Please enter a valid|couldn.t be found|not recognized/i.test(t) };
      });
      if (state.val === '' && !state.bad) return 'OK';
      if (state.bad) return 'REJECTED';
    } else {
      return 'TYPO:' + val;
    }
  }
  return 'FAILED';
}

async function fillBody(page, text) {
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].length) await page.keyboard.insertText(lines[i]);
    if (i < lines.length - 1) await page.keyboard.press('Enter');
  }
}

(async () => {
  const { page } = await L.attach();
  await page.goto('https://mail.google.com/mail/u/0/#inbox', { waitUntil: 'load', timeout: 90000 });
  await page.waitForTimeout(6000);

  for (const d of MAN) {
    if (sent[d.id] && sent[d.id].result === 'SENT') { console.log(`[${d.id}] already sent`); continue; }
    if (sentAddrs.has(String(d.to).toLowerCase())) { console.log(`[${d.id}] address already emailed - skipping`); continue; }
    let body = fs.readFileSync(path.join(ROOT, d.file), 'utf8').trim();
    const sm = body.match(/^Subject:[ \t]*(.*)\r?\n+/i);   // body files may carry their subject on line 1
    if (sm) { if (!d.subject) d.subject = sm[1].trim(); body = body.slice(sm[0].length).trim(); }
    if (!d.subject) { console.log(`[${d.id}] ABORT no subject`); continue; }
    const att = path.join(ROOT, d.attach);
    const rec = { to: d.to, result: 'PENDING', at: new Date().toISOString(), note: '' };
    try {
      if (!await openCompose(page)) { rec.result = 'ERROR'; rec.note = 'compose would not open'; }
      else {
        const t = await setTo(page, d.to);
        if (t !== 'OK') {
          rec.result = 'ABORT'; rec.note = 'to:' + t;
          console.log(`[${d.id}] ABORT to=${t}`);
          await page.keyboard.press('Escape'); await page.waitForTimeout(1200);
        } else {
          const sub = await page.$('input[name="subjectbox"]');
          await sub.click({ timeout: 10000 });
          await page.keyboard.insertText(d.subject);
          await page.waitForTimeout(400);
          const eb = await page.$('div[aria-label="Message Body"]');
          await eb.click({ timeout: 10000 });
          await page.waitForTimeout(300);
          await fillBody(page, body);
          await page.waitForTimeout(700);

          const fi = await page.$('input[type=file]');
          await fi.setInputFiles(att);
          let attOk = false;
          for (let i = 0; i < 30; i++) {
            await page.waitForTimeout(900);
            attOk = await page.evaluate(() => {
              const t = document.body.innerText;
              return /\.pdf/i.test(t) && !/Uploading|Attaching/i.test(t);
            });
            if (attOk) break;
          }
          if (!attOk) {
            rec.result = 'ABORT'; rec.note = 'no attachment';
            console.log(`[${d.id}] ABORT attachment`);
            await page.keyboard.press('Escape'); await page.waitForTimeout(1200);
          } else {
            await page.evaluate(() => {
              const b = [...document.querySelectorAll('div[role="button"]')]
                .find(e => /^send\b/i.test(e.getAttribute('aria-label') || ''));
              if (b) b.click();
            });
            await page.waitForTimeout(5000);
            if (await page.$('div[aria-label="Message Body"]')) {
              await page.keyboard.press('Control+Enter');
              await page.waitForTimeout(6000);
            }
            const still = await page.$('div[aria-label="Message Body"]');
            rec.result = still ? 'UNSURE' : 'SENT';
            rec.note = still ? 'compose still open' : 'compose closed';
            console.log(`[${d.id}] ${rec.result} -> ${d.to}`);
            await page.screenshot({ path: path.join(SHOTS, 's_' + d.id + '.png') }).catch(() => {});
          }
        }
      }
    } catch (e) {
      rec.result = 'ERROR'; rec.note = String(e.message).slice(0, 90);
      console.log(`[${d.id}] ERROR ${rec.note}`);
      await page.keyboard.press('Escape').catch(() => {});
      await page.waitForTimeout(1500);
    }
    sent[d.id] = rec;
    fs.writeFileSync(SENTF, JSON.stringify(sent, null, 1));
    if (rec.result !== 'SENT') { await page.goto('https://mail.google.com/mail/u/0/#inbox', { waitUntil: 'load' }).catch(() => {}); await page.waitForTimeout(3000); }
    await sleep(rand(8000, 14000));
  }

  const tally = Object.values(sent).reduce((a, r) => (a[r.result] = (a[r.result] || 0) + 1, a), {});
  console.log('\nTALLY', JSON.stringify(tally));
  Object.entries(sent).forEach(([k, v]) => { if (v.result !== 'SENT') console.log('  pending:', k, v.result, v.note); });
  L.done();
})();
