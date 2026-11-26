// Discards Gmail drafts that have NO subject AND whose recipient is one of the given addresses. Usage: node draftclean.js addr1 addr2 ...
const L = require('./lib');
(async () => {
  const want = process.argv.slice(2).map(a => a.toLowerCase());
  const { page } = await L.attach();
  await page.goto('https://mail.google.com/mail/u/0/#drafts', { waitUntil: 'load', timeout: 90000 });
  await page.waitForTimeout(6000);
  const rows = page.locator('div[role="main"] tr.zA');
  const n = await rows.count(); let picked = 0;
  for (let i = 0; i < n; i++) {
    const r = rows.nth(i);
    const info = await r.evaluate(tr => ({ subj: ((tr.querySelector('.bog') || {}).innerText || '').trim(),
      to: [...tr.querySelectorAll('span[email]')].map(s => s.getAttribute('email').toLowerCase()), vis: !!tr.offsetParent }));
    if (!info.vis) continue;
    const match = (info.subj === '' || info.subj === '(no subject)') && info.to.length && info.to.every(t => want.includes(t));
    console.log(i, JSON.stringify(info), match ? 'SELECT' : '');
    if (match) { await r.locator('div[role="checkbox"]').first().click(); picked++; await page.waitForTimeout(300); }
  }
  if (picked) {
    await page.locator('div[role="button"]').filter({ hasText: /^Discard drafts$/ }).first().click({ timeout: 10000 });
    await page.waitForTimeout(3000); console.log('discarded', picked);
  }
  L.done();
})();
