// node wa_batch.js <manifest.json>   manifest: [{id, phone (intl digits), file (text), attach (pdf)}]
// Per number: open chat via /send?phone=, ABORT if the chat already contains any message from us, type text, Enter,
// then Attach > Document > PDF > Send. Records into outbox/sent_all.json (shared guard). 60-100 s spacing between numbers.
const fs = require('fs'), path = require('path'), L = require('./lib');
const ROOT = path.resolve(__dirname, '..', '..');
const MAN = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const SENTF = path.join(ROOT, 'outbox', 'sent_all.json');
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const { browser } = await L.attach();
  const ctx = browser.contexts()[0];
  let page = ctx.pages().find(p => p.url().includes('web.whatsapp.com')) || await ctx.newPage();
  await page.bringToFront();
  for (const m of MAN) {
    const sent = JSON.parse(fs.readFileSync(SENTF, 'utf8'));
    const key = 'whatsapp:+' + m.phone;
    if (Object.values(sent).some(v => v.to === key && v.result !== 'ERROR')) { console.log(`[${m.id}] already in guard - skip`); continue; }
    const rec = { to: key, result: 'ERROR', at: new Date().toISOString(), note: '' };
    try {
      await page.goto('https://web.whatsapp.com/send?phone=' + m.phone, { waitUntil: 'load', timeout: 90000 });
      let box = null;
      for (let i = 0; i < 60 && !box; i++) {
        await page.waitForTimeout(1500);
        const bad = await page.evaluate(() => /phone number shared via url is invalid|isn.t on WhatsApp|not on WhatsApp/i.test(document.body.innerText));
        if (bad) break;
        box = await page.$('footer [contenteditable="true"]');
      }
      if (!box) { rec.result = 'NOT_ON_WA'; rec.note = 'no chat box / number invalid'; throw new Error('skip'); }
      await page.waitForTimeout(4000);
      const main = await page.evaluate(() => (document.querySelector('#main') || {}).innerText || '');
      if (L.NAME && (main.includes(L.NAME) || main.includes(L.NAME.split(' ')[0] + "'s Resume"))) { rec.result = 'SKIP_EXISTING'; rec.note = 'chat already has our message'; throw new Error('skip'); }
      const msg = fs.readFileSync(path.join(ROOT, m.file), 'utf8').trim();
      await box.click();
      const lines = msg.split('\n');
      for (let i = 0; i < lines.length; i++) { if (lines[i]) await page.keyboard.insertText(lines[i]); if (i < lines.length - 1) await page.keyboard.press('Shift+Enter'); }
      await page.waitForTimeout(800); await page.keyboard.press('Enter'); await page.waitForTimeout(4000);
      await page.locator('footer [aria-label="Attach"]').first().click(); await page.waitForTimeout(1500);
      const [fc] = await Promise.all([page.waitForEvent('filechooser', { timeout: 15000 }), page.getByText('Document', { exact: true }).first().click()]);
      await fc.setFiles(path.join(ROOT, m.attach));
      let ok = false;
      for (let i = 0; i < 20 && !ok; i++) {
        await page.waitForTimeout(1500);
        const b = page.locator('div[aria-label="Send"], button[aria-label="Send"], [aria-label^="Send 1"], span[data-icon="send"], span[data-icon="wds-ic-send-filled"]').last();
        if (await b.count() && await b.isVisible()) { await b.click(); ok = true; }
      }
      await page.waitForTimeout(8000);
      const after = await page.evaluate(() => (document.querySelector('#main') || {}).innerText || '');
      rec.result = 'SENT';
      rec.note = 'text sent; pdf send clicked=' + ok + '; pdf visible=' + (L.NAME ? after.includes(L.NAME.split(' ')[0] + "'s Resume") : /\.pdf/i.test(after)) + ' (WA Web may lag; verify on phone)';
    } catch (e) { if (e.message !== 'skip') rec.note = String(e.message).slice(0, 100); }
    const s2 = JSON.parse(fs.readFileSync(SENTF, 'utf8')); s2[m.id] = rec; fs.writeFileSync(SENTF, JSON.stringify(s2, null, 1));
    console.log(`[${m.id}] ${rec.result} ${key} ${rec.note}`);
    await sleep(60000 + Math.floor(Math.random() * 40000));
  }
  L.done();
})();
