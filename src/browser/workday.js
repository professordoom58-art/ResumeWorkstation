const L = require('./lib');

// Workday helpers. Applicant data lives in profile/workday.json (gitignored; see profile/workday.example.json).
const fs = require('fs'), path = require('path');
const WD_F = path.join(__dirname, '..', '..', 'profile', 'workday.json');
if (!fs.existsSync(WD_F)) throw new Error('missing ' + WD_F + ' - copy profile/workday.example.json and fill it from the resume');
const WD = JSON.parse(fs.readFileSync(WD_F, 'utf8'));
const WORK = WD.work, EDUS = WD.education, ME = WD.myInfo;

const stepText = (page) => page.evaluate(() => {
  const m = document.body.innerText.match(/current step \d of \d\s*\n([^\n]+)/);
  return m ? m[1].trim() : '';
});

async function selectOption(page, sel, wanted) {
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(400);
  for (let attempt = 0; attempt < 3; attempt++) {
    const el = await page.$(sel);
    if (!el) return { ok: false, why: 'no-el' };
    await el.scrollIntoViewIfNeeded().catch(() => {});
    await el.click({ force: true }).catch(() => {});
    await page.waitForTimeout(2000);
    const r = await page.evaluate((w) => {
      const norm = (s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
      const all = [...document.querySelectorAll('li[data-automation-id=menuItem], li[role=option], li, div[data-automation-id=promptOption]')]
        .filter(e => (e.innerText || '').trim() && e.getBoundingClientRect().width > 1);
      const t = all.find(e => norm(e.innerText) === norm(w))
        || all.find(e => norm(e.innerText).includes(norm(w)));
      if (!t) return { ok: false, saw: all.map(e => e.innerText.trim()).slice(0, 8) };
      const b = t.getBoundingClientRect();
      return { ok: true, picked: t.innerText.trim(), x: b.left + b.width / 2, y: b.top + b.height / 2 };
    }, wanted);
    if (r.ok) {
      // real mouse chord - Workday ignores synthetic clicks on option rows
      await page.mouse.move(r.x, r.y);
      await page.waitForTimeout(150);
      await page.mouse.down();
      await page.waitForTimeout(110);
      await page.mouse.up();
      await page.waitForTimeout(1200);
      const committed = await page.evaluate((s) => {
        const e = document.querySelector(s);
        const t = (e?.innerText || '').replace(/\s+/g, ' ').trim();
        return t && !/select one|expanded/i.test(t) ? t : '';
      }, sel);
      if (committed) return { ok: true, picked: r.picked, committed };
      // try keyboard commit as fallback
      await page.keyboard.press('Enter').catch(() => {});
      await page.waitForTimeout(1200);
      return { ok: true, picked: r.picked, committed: 'unconfirmed' };
    }
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(500);
  }
  return { ok: false, why: 'retries-exhausted' };
}

const next = async (page) => {
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(300);
  await L.wdClick(page, '[data-automation-id=pageFooterNextButton]');
  await page.waitForTimeout(9000);
};

async function ksSet(page, sel, val) {
  const el = await page.$(sel);
  if (!el) return false;
  const cur = await el.inputValue().catch(() => '');
  if (cur === val) return true;
  for (let i = 0; i < 3; i++) {
    await el.click({ clickCount: 3 }).catch(() => {});
    await page.keyboard.press('Control+A').catch(() => {});
    await page.keyboard.press('Delete').catch(() => {});
    await page.waitForTimeout(180);
    await el.type(val, { delay: 40 }).catch(() => {});
    await page.waitForTimeout(220);
    if ((await el.inputValue().catch(() => '')) === val) return true;
  }
  return false;
}

async function fillMyInfo(page) {
  await ksSet(page, '#name--legalName--firstName', ME.firstName);
  await ksSet(page, '#name--legalName--lastName', ME.lastName);
  await ksSet(page, '#address--addressLine1', ME.addressLine1);
  await ksSet(page, '#address--city', ME.city);
  await ksSet(page, '#address--postalCode', ME.postalCode);
  await ksSet(page, '#phoneNumber--phoneNumber', ME.phone);
  await page.waitForTimeout(400);

  const region = await page.$('#address--countryRegion');
  if (region) {
    const cur = (await region.innerText()).trim();
    if (!cur || /select one/i.test(cur)) await selectOption(page, '#address--countryRegion', ME.region);
  }
  const src = await page.$('#source--source');
  if (src) {
    const r = await selectOption(page, '#source--source', ME.source || 'Job Board');
    console.log('   source:', JSON.stringify(r));
  }

  // "previously worked here" -> No
  await page.evaluate(() => {
    const no = [...document.querySelectorAll('label,span,div')]
      .find(e => e.children.length === 0 && (e.innerText || '').trim() === 'No' && e.getBoundingClientRect().width > 1);
    if (no) no.click();
  });
  await page.waitForTimeout(600);
}

async function fillExperience(page) {
  const counts = await page.evaluate(() => document.querySelectorAll('input[id*=workExperience-][id*=companyName]').length);
  const need = WORK.length - counts;
  for (let k = 0; k < need; k++) {
    const bs = await page.$$('button[data-automation-id=add-button]');
    if (bs[0]) await bs[0].click();
    await page.waitForTimeout(2500);
  }
  const filled = await page.evaluate((WORK) => {
    const idxs = [...document.querySelectorAll('input[id*=workExperience-][id*=companyName]')]
      .map(e => (e.id.match(/workExperience-(\d+)--/) || [])[1]).filter(Boolean).map(Number).sort((a, b) => a - b);
    const out = [];
    idxs.forEach((i, k) => {
      const d = WORK[k]; if (!d) return;
      const pre = `#workExperience-${i}--`;
      const q = (s) => document.querySelector(s);
      const put = (s, v) => { const el = q(s); if (el) { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); } };
      put(pre + 'jobTitle', d.title);
      put(pre + 'companyName', d.company);
      put(pre + 'location', d.location);
      put(pre + 'roleDescription', d.desc);
      put(`${pre}startDate-dateSectionMonth-input`, d.fromM);
      put(`${pre}startDate-dateSectionYear-input`, d.fromY);
      if (!d.current) {
        put(`${pre}endDate-dateSectionMonth-input`, d.toM);
        put(`${pre}endDate-dateSectionYear-input`, d.toY);
      }
      const cb = q(pre + 'currentlyWorkHere');
      if (d.current && cb && !cb.checked) cb.click();
      out.push(i);
    });
    return out;
  }, WORK);
  await page.waitForTimeout(1200);
  return filled;
}

async function fillEducation(page) {
  const counts = await page.evaluate(() => document.querySelectorAll('input[id*=education-][id*=schoolName]').length);
  const need = EDUS.length - counts;
  for (let k = 0; k < need; k++) {
    const bs = await page.$$('button[data-automation-id=add-button]');
    if (bs[1]) await bs[1].click();
    await page.waitForTimeout(2500);
  }
  const idxs = await page.evaluate(() => [...document.querySelectorAll('input[id*=education-][id*=schoolName]')]
    .map(e => (e.id.match(/education-(\d+)--/) || [])[1]).filter(Boolean).map(Number).sort((a, b) => a - b));
  for (let k = 0; k < idxs.length && k < EDUS.length; k++) {
    const i = idxs[k], d = EDUS[k];
    await page.fill(`#education-${i}--schoolName`, d.school).catch(() => {});
    await page.waitForTimeout(700);
    await page.keyboard.press('Escape').catch(() => {});
    await selectOption(page, `#education-${i}--degree`, d.degree);
    await page.fill(`#education-${i}--gradeAverage`, d.gpa).catch(() => {});
    await page.fill(`#education-${i}--firstYearAttended-dateSectionYear-input`, d.from).catch(() => {});
    await page.fill(`#education-${i}--lastYearAttended-dateSectionYear-input`, d.to).catch(() => {});
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(300);
  }
}

async function uploadResume(page, pdf) {
  const fi = await page.$$('input[type=file]');
  if (fi.length) { await fi[0].setInputFiles(pdf); await page.waitForTimeout(9000); }
  return await page.evaluate(() => {
    const t = document.body.innerText;
    return /Successfully Uploaded/i.test(t) ? 'uploaded' : 'check';
  });
}

async function answerQuestions(page) {
  const list = await page.evaluate(() => [...document.querySelectorAll('button[id^=primaryQuestionnaire--]')]
    .filter(b => b.getBoundingClientRect().width > 1)
    .map(b => {
      let n = b, q = '';
      for (let k = 0; k < 8 && n; k++) { n = n.parentElement; if (n && /\?/.test(n.innerText || '')) { q = n.innerText.split('\n')[0]; break; } }
      return { id: b.id, q, cur: (b.innerText || '').trim() };
    }));
  const out = [];
  for (const x of list) {
    if (x.cur && !/select one/i.test(x.cur)) { out.push([x.q.slice(0, 45), 'already:' + x.cur]); continue; }
    const yes = /authori[sz]ed for employment|willing to (relocate|travel)|legally (authori[sz]ed|entitled)|eligible to work/i.test(x.q);
    const r = await selectOption(page, '#' + x.id, yes ? 'Yes' : 'No');
    out.push([x.q.slice(0, 45), (yes ? 'Yes' : 'No') + ':' + JSON.stringify(r)]);
  }
  return out;
}

async function fillDisclosures(page) {
  const out = {};
  const sel = await page.evaluate(() => {
    for (const b of document.querySelectorAll('button')) {
      const t = (b.innerText || '').trim();
      if (/select one/i.test(t) && /gender|race|ethnic|veteran|disabilit/i.test(
        (b.getAttribute('aria-label') || '') + b.id + (b.closest('div')?.innerText || ''))) return b.id;
    }
    return null;
  });
  if (sel) {
    const want = await page.evaluate(() => {
      const t = document.body.innerText;
      if (/Not declared/i.test(t)) return 'Not declared';
      if (/I don't wish|prefer not to/i.test(t)) return "I don't wish to answer";
      return null;
    });
    if (want) out.gender = await selectOption(page, '#' + sel, want);
  }
  await page.evaluate(() => {
    for (const c of document.querySelectorAll('input[type=checkbox]')) {
      const id = c.id || '';
      const ctx = (c.closest('div')?.innerText || '') + id;
      if (/terms|consent|acknowledge|agree/i.test(ctx) && !c.checked) c.click();
    }
  });
  await page.waitForTimeout(800);
  return out;
}

module.exports = { ksSet, selectOption, WORK, EDUS, stepText, selectOption, next, fillMyInfo, fillExperience, fillEducation, uploadResume, answerQuestions, fillDisclosures };
