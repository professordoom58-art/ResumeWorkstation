// Usage: node searchsent.js <manifest.json> [extra gmail queries...]
// For each manifest recipient runs Gmail search `in:sent to:<addr>` and prints the hit count.
const fs = require('fs'), L = require('./lib');
const MAN = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const extra = process.argv.slice(3);
(async () => {
  const { page } = await L.attach();
  const qs = MAN.map(m => ({ label: m.id + ' ' + m.to, q: 'in:sent to:' + m.to }))
    .concat(extra.map(q => ({ label: 'Q', q })));
  const out = [];
  for (const { label, q } of qs) {
    await page.goto('https://mail.google.com/mail/u/0/#search/' + encodeURIComponent(q), { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(5500);
    const r = await page.evaluate(() => {
      const main = document.querySelector('div[role="main"]');
      const rows = main ? [...main.querySelectorAll('tr.zA')].filter(tr => tr.offsetParent !== null) : [];
      return rows.slice(0, 5).map(tr => ((tr.querySelector('.bog') || {}).innerText || '').trim() + ' @ ' +
        (((tr.querySelector('.xW span') || {}).getAttribute || (() => '')).call(tr.querySelector('.xW span') || {}, 'title') || ''));
    });
    console.log(`${r.length ? 'HIT x' + r.length : 'none '} | ${label} | ${q}` + (r.length ? '\n     ' + r.join('\n     ') : ''));
    out.push({ label, q, hits: r });
  }
  fs.writeFileSync(require('path').join(__dirname, '..', '..', 'outbox', 'searchsent_last.json'), JSON.stringify(out, null, 1));
  L.done();
})();
