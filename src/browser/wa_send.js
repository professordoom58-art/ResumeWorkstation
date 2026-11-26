// node wa_send.js <phone-intl-digits> <msg.txt> <file.pdf>
const fs=require('fs'),path=require('path'),L=require('./lib');
const [phone,msgf,pdf]=process.argv.slice(2);
const msg=fs.readFileSync(msgf,'utf8').trim();
(async()=>{const{browser}=await L.attach();const ctx=browser.contexts()[0];
let page=ctx.pages().find(p=>p.url().includes('web.whatsapp.com'))||await ctx.newPage();
await page.bringToFront();
await page.goto('https://web.whatsapp.com/send?phone='+phone,{waitUntil:'load',timeout:90000});
let box=null;for(let i=0;i<80&&!box;i++){await page.waitForTimeout(1500);box=await page.$('footer div[contenteditable="true"]');}
if(!box){console.log('NO CHAT');return L.done();}
const before=await page.$$eval('#main div.message-out',e=>e.length);
if(before>0){console.log('ABORT: chat already has',before,'outgoing messages');return L.done();}
await box.click();
const lines=msg.split('\n');
for(let i=0;i<lines.length;i++){ if(lines[i]) await page.keyboard.insertText(lines[i]); if(i<lines.length-1) await page.keyboard.press('Shift+Enter'); }
await page.waitForTimeout(800); await page.keyboard.press('Enter'); await page.waitForTimeout(3000);
// attach document
const attach=page.locator('footer button[title="Attach"], footer [aria-label="Attach"], footer span[data-icon="plus-rounded"], footer span[data-icon="plus"]').first();
await attach.click({timeout:15000}); await page.waitForTimeout(1500);
const inputs=await page.$$('input[type="file"]'); let set=false;
for(const inp of inputs){const acc=await inp.getAttribute('accept'); if(acc==='*'||(acc&&!/image|video/.test(acc))||!acc){await inp.setInputFiles(path.resolve(pdf)); set=true; break;}}
if(!set){console.log('NO DOC INPUT', await Promise.all(inputs.map(i=>i.getAttribute('accept'))));return L.done();}
let sent=false;
for(let i=0;i<20&&!sent;i++){await page.waitForTimeout(1500);
  const b=page.locator('div[aria-label="Send"], span[data-icon="send"], span[data-icon="wds-ic-send-filled"]').last();
  if(await b.count()){await b.click().catch(()=>{});sent=true;}}
await page.waitForTimeout(8000);
const out=await page.$$eval('#main div.message-out',e=>e.map(x=>x.innerText.replace(/\s+/g,' ').slice(0,90)));
const pending=await page.$$eval('#main div.message-out span[data-icon="msg-time"]',e=>e.length);
console.log('outgoing',out.length,'pending',pending); out.forEach(o=>console.log('  >',o));
await page.screenshot({path:path.join(__dirname,'shots','wa_sent_'+phone+'.png')});
L.done();})();
