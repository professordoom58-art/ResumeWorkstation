// Usage: node listmail.js "<gmail query>" -> lists sender | subject | date of visible rows
const L = require('./lib');
(async () => {
  const { page } = await L.attach();
  for (const q of process.argv.slice(2)) {
    await page.goto('https://mail.google.com/mail/u/0/#search/' + encodeURIComponent(q), { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(6000);
    const r = await page.evaluate(() => {
      const main = document.querySelector('div[role="main"]');
      return main ? [...main.querySelectorAll('tr.zA')].filter(t => t.offsetParent).map(tr =>
        [(tr.querySelector('.yW span[email]')||{}).getAttribute?.call(tr.querySelector('.yW span[email]')||document.createElement('a'),'email')||'', (tr.querySelector('.bog')||{}).innerText||'', (tr.querySelector('.y2')||{}).innerText||'', (tr.querySelector('.xW span')||{}).title||''].join(' | ')) : [];
    });
    console.log('### ' + q + ' -> ' + r.length); r.forEach(x => console.log('  ' + x.slice(0, 230)));
  }
  L.done();
})();
