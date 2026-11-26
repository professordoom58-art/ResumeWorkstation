// node wa_list.js [n] — opens web.whatsapp.com if needed and lists the top n chats (title | preview)
const L=require('./lib');
(async()=>{const{browser}=await L.attach();const ctx=browser.contexts()[0];
let p=ctx.pages().find(p=>p.url().includes('web.whatsapp.com'));
if(!p){p=await ctx.newPage();await p.goto('https://web.whatsapp.com/',{waitUntil:'load',timeout:90000});}
for(let i=0;i<40;i++){if(await p.$('#pane-side'))break;await p.waitForTimeout(1500);}
await p.waitForTimeout(3000);
const rows=await p.evaluate(()=>[...document.querySelectorAll('#pane-side [role=listitem], #pane-side [role=row]')].map(e=>e.innerText.replace(/\s+/g,' ').slice(0,170)));
rows.slice(0,+(process.argv[2]||12)).forEach(r=>console.log('-',r));L.done();})();
