// Usage: node readmail.js "<gmail query>" [maxThreads]  -> prints sender + body text of first N threads
const L = require('./lib');
(async () => {
  const { page } = await L.attach();
  const q = process.argv[2], n = +(process.argv[3] || 1);
  for (let i = 0; i < n; i++) {
    await page.goto('https://mail.google.com/mail/u/0/#search/' + encodeURIComponent(q), { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(5000);
    const rows = page.locator('div[role="main"] tr.zA');
    if (await rows.count() <= i) break;
    await rows.nth(i).click();
    await page.waitForTimeout(4000);
    const t = await page.evaluate(() => {
      const h = document.querySelector('h2.hP'); const f = [...document.querySelectorAll('span.gD')].map(e => e.getAttribute('email') + ' (' + e.innerText + ')');
      const b = [...document.querySelectorAll('div.a3s')].map(e => e.innerText).join('\n---\n');
      return (h ? h.innerText : '') + '\nFROM: ' + f.join(', ') + '\n' + b;
    });
    console.log('=========', i, '\n' + t.slice(0, 3500));
  }
  L.done();
})();
