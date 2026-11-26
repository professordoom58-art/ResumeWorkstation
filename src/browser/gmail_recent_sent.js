const L=require('./lib');
(async()=>{const{page}=await L.attach();
await page.goto('https://mail.google.com/mail/u/0/#sent',{waitUntil:'load',timeout:90000});
await page.waitForTimeout(3000); await page.reload({waitUntil:'load'}); await page.waitForTimeout(6000);
const rows=await page.evaluate(()=>[...document.querySelectorAll('tr.zA')].slice(0,15).map(tr=>({
  to:[...tr.querySelectorAll('.yW span[email],.yX span[email]')].map(e=>e.getAttribute('email')).join(','),
  subj:((tr.querySelector('.bog')||{}).innerText||'').slice(0,70),
  date:((tr.querySelector('.xW span')||{}).getAttribute&&(tr.querySelector('.xW span')||{}).getAttribute('title'))||((tr.querySelector('.xW')||{}).innerText||'')
})));
rows.forEach((r,i)=>console.log(i+1,'|',r.to,'|',r.date,'|',r.subj));
L.done();})();
