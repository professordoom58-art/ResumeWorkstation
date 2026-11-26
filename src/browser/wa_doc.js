// node wa_doc.js "<chat title>" <file.pdf> — chat must be open; attaches a document via Attach > Document (filechooser)
const path=require('path'),L=require('./lib');
const [title,pdf]=process.argv.slice(2);
(async()=>{const{browser}=await L.attach();const page=browser.contexts()[0].pages().find(p=>p.url().includes('web.whatsapp.com'));
const hdr=await page.evaluate(()=>{const h=document.querySelector('#main header');return h?h.innerText:''});
if(!hdr.includes(title)){console.log('ABORT wrong chat:',hdr);return L.done();}
if(/\.pdf/i.test(await page.evaluate(()=>document.querySelector('#main').innerText))){console.log('ABORT: PDF already in chat');return L.done();}
await page.locator('footer [aria-label="Attach"]').first().click(); await page.waitForTimeout(1500);
const items=await page.evaluate(()=>[...document.querySelectorAll('[role="application"] li, [role="menu"] [role="menuitem"], li[role="button"], div[role="button"]')].map(e=>e.innerText.trim()).filter(t=>t&&t.length<30));
console.log('menu',JSON.stringify(items.slice(0,15)));
let inp=await page.$('input[type=file][accept="*"]');
if(inp){await inp.setInputFiles(path.resolve(pdf));}
else{const [fc]=await Promise.all([page.waitForEvent('filechooser',{timeout:10000}),page.getByText('Document',{exact:true}).first().click()]);await fc.setFiles(path.resolve(pdf));}
let ok=false;
for(let i=0;i<20&&!ok;i++){await page.waitForTimeout(1500);
  const b=page.locator('div[aria-label="Send"], button[aria-label="Send"], [aria-label^="Send 1"], span[data-icon="send"], span[data-icon="wds-ic-send-filled"]').last();
  if(await b.count()&&await b.isVisible()){await b.click();ok=true;}}
console.log('send clicked',ok); await page.waitForTimeout(12000);
console.log((await page.evaluate(()=>document.querySelector('#main').innerText.replace(/\s+/g,' '))).slice(-250));
await page.screenshot({path:path.join(__dirname,'shots','wa_doc.png')}); L.done();})();
