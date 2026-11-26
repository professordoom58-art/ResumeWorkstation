const { chromium } = require('playwright-core');
const PORT = process.env.CDP_PORT || '9223';
async function attach() {
  const browser = await chromium.connectOverCDP('http://127.0.0.1:' + PORT);
  const ctx = browser.contexts()[0];
  const pages = ctx.pages();
  const page = pages[pages.length - 1] || await ctx.newPage();
  page.setDefaultTimeout(45000);
  return { browser, ctx, page };
}
module.exports = { attach };
