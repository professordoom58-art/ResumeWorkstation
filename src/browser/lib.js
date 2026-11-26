const { attach } = require('./attach');

const fs = require('fs'), path = require('path');
// Applicant identity comes from profile/resume_base.json (written from the attached resume; gitignored).
const PROFILE_F = path.join(__dirname, '..', '..', 'profile', 'resume_base.json');
const PROFILE = fs.existsSync(PROFILE_F) ? JSON.parse(fs.readFileSync(PROFILE_F, 'utf8')) : {};
const EMAIL = process.env.APPLICANT_EMAIL || (PROFILE.contact || {}).email || '';
const NAME = process.env.APPLICANT_NAME || (PROFILE.name ? PROFILE.name.replace(/\w+/g, w => w[0] + w.slice(1).toLowerCase()) : '');

// Click whatever element is on top at the centre of `sel` (Workday puts an
// invisible click_filter div over real buttons), else dispatch on the element.
// Real mouse down/up chord - Workday ignores synthetic .click() on many buttons.
async function wdClick(page, sel) {
  const el = await page.$(sel);
  if (!el) return 'no-el';
  try { await el.scrollIntoViewIfNeeded(); } catch (e) {}
  await page.waitForTimeout(250);
  let box = await el.boundingBox().catch(() => null);
  if (!box) {
    return await page.evaluate((sel) => {
      const e2 = document.querySelector(sel);
      if (!e2) return 'no-el';
      e2.click();
      return 'js-fallback';
    }, sel);
  }
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  // if something covers the point, try the top element instead
  const covered = await page.evaluate(([x, y, sel]) => {
    const el2 = document.querySelector(sel);
    const top = document.elementFromPoint(x, y);
    return !!(top && top !== el2 && !el2.contains(top));
  }, [x, y, sel]);
  await page.mouse.move(x, y);
  await page.waitForTimeout(120);
  await page.mouse.down();
  await page.waitForTimeout(120);
  await page.mouse.up();
  return covered ? 'chord-overlay' : 'chord';
}

async function text(page, n = 1200) {
  return await page.evaluate((n) => document.body.innerText.replace(/\n{2,}/g, '\n').slice(0, n), n);
}

async function fields(page) {
  return await page.evaluate(() => [...document.querySelectorAll('input,select,textarea,button[data-automation-id],[role=combobox]')]
    .filter(e => e.getBoundingClientRect().width > 1)
    .map(e => ({
      aid: e.getAttribute('data-automation-id') || '',
      tag: e.tagName.toLowerCase(),
      type: e.type || '',
      req: e.getAttribute('aria-required') === 'true',
      val: (e.value || '').slice(0, 34),
      lab: (e.labels && e.labels[0] ? e.labels[0].innerText : '') || '',
      txt: (e.innerText || '').trim().slice(0, 30),
    })));
}

async function signIn(page, loginUrl, pw) {
  await page.goto(loginUrl, { waitUntil: 'load', timeout: 90000 });
  await page.waitForTimeout(6000);
  if (await page.$('[data-automation-id=email]')) {
    await page.fill('[data-automation-id=email]', EMAIL);
    await page.fill('[data-automation-id=password]', pw);
    await page.waitForTimeout(400);
    const r = await wdClick(page, '[data-automation-id=signInSubmitButton]');
    await page.waitForTimeout(13000);
    return 'attempted:' + r + ' -> ' + page.url();
  }
  return 'no-form -> ' + page.url();
}

function done() { setTimeout(() => process.exit(0), 300); }

module.exports = { attach, wdClick, text, fields, signIn, done, EMAIL, NAME };
