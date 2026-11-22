// A browser check of the built page (needs Playwright): opens every lazily loaded tab, drives their controls, opens stocks and the watchlist, and writes what it saw to $OUT as JSON.
// Run it before and after a change to the page and compare the two files; any difference is a behaviour change. Errors in the page are listed under "errors".
//   PAGE=$PWD/site/index.html OUT=/tmp/after.json node tests/browser/check.js
const {chromium}=require('playwright');const fs=require('fs');
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1300,height:1000}});const errs=[];p.on('pageerror',x=>errs.push(x.message));
await p.goto('file://'+process.env.PAGE);await p.waitForTimeout(2500);
const obs={};const ev=(k,f,a)=>p.evaluate(f,a).then(v=>{obs[k]=v}).catch(e=>{obs[k]='ERR '+e.message.slice(0,80)});
const tab=n=>p.evaluate(n=>{[...document.querySelectorAll('.tab')].find(x=>x.textContent.trim()===n).click()},n).then(()=>p.waitForTimeout(150));
const click=(sel,i=0)=>p.evaluate(([s,i])=>{const e=document.querySelectorAll(s)[i];if(e)e.click();return !!e},[sel,i]).then(()=>p.waitForTimeout(80));
const vis=sel=>p.evaluate(s=>[...document.querySelectorAll(s)].filter(e=>!e.hidden&&e.closest('[hidden]')==null).length,sel);
// --- 52W highs
await tab('52W HIGHS'); obs.h52_groups_default=await vis('#p-high52 .h52group'); obs.h52_cards_default=await vis('#p-high52 .h52card');
await click('#p-high52 .h52tab',1); obs.h52_groups_after_tab=await vis('#p-high52 .h52group'); obs.h52_which=await p.evaluate(()=>[...document.querySelectorAll('#p-high52 .h52group')].find(g=>!g.hidden)?.dataset.h52Group);
await click('#p-high52 .h52cap',1); obs.h52_cards_after_cap=await vis('#p-high52 .h52card');
// --- technical patterns
await tab('TECHNICAL PATTERNS'); obs.pt_digest=await p.evaluate(()=>document.querySelector('.ptdigest')?.innerText.length>50);
obs.pt_wlline=await p.evaluate(()=>document.getElementById('pt-wl')?.innerText||'');
for(const s of ['ASCENDING TRIANGLE','DESCENDING TRIANGLE','RECTANGLE','BREAKOUT BASES','SHORT IDEAS']){await p.evaluate(s=>{[...document.querySelectorAll('#p-patterns > .subtabs .subtab')].find(x=>x.textContent===s).click()},s);await p.waitForTimeout(80);
 obs['pt_sub_'+s]=await p.evaluate(()=>document.querySelector('#p-patterns > .subview:not([hidden])').dataset.sub)}
await p.evaluate(()=>{[...document.querySelectorAll('#p-patterns > .subtabs .subtab')].find(x=>x.textContent==='ASCENDING TRIANGLE').click()});await p.waitForTimeout(80);
obs.pt_rows_default=await vis('#p-patterns > .subview:not([hidden]) .ptview:not([hidden]) tbody tr[data-status]');
await p.evaluate(()=>document.querySelector('#p-patterns > .subview:not([hidden]) .ptchip[data-st="ALL"]').click());obs.pt_rows_all=await vis('#p-patterns > .subview:not([hidden]) .ptview:not([hidden]) tbody tr[data-status]');
await p.evaluate(()=>document.querySelector('#p-patterns > .subview:not([hidden]) .ptchip[data-fo]').click());obs.pt_rows_all_fo=await vis('#p-patterns > .subview:not([hidden]) .ptview:not([hidden]) tbody tr[data-status]');
await p.evaluate(()=>document.querySelector('#p-patterns > .subview:not([hidden]) .ptfbtn[data-tf="weekly"]').click());obs.pt_weekly_view=await p.evaluate(()=>[...document.querySelectorAll('#p-patterns > .subview:not([hidden]) .ptview')].find(v=>!v.hidden).dataset.tf);
await p.evaluate(()=>{[...document.querySelectorAll('#p-patterns > .subtabs .subtab')].find(x=>x.textContent==='BREAKOUT BASES').click()});await p.waitForTimeout(80);
obs.bases_cards_default=await vis('#p-bases .basecard');await click('#p-bases .basetab',1);obs.bases_group_after_tab=await p.evaluate(()=>[...document.querySelectorAll('#p-bases .basegroup')].find(g=>!g.hidden)?.dataset.baseGroup);
await click('#p-bases .basefilter',0);obs.bases_cards_after_filter=await vis('#p-bases .basecard');
await p.evaluate(()=>{[...document.querySelectorAll('#p-patterns > .subtabs .subtab')].find(x=>x.textContent==='SHORT IDEAS').click()});await p.waitForTimeout(80);
await p.evaluate(()=>{[...document.querySelectorAll('#p-patterns > .subview:not([hidden]) .subtab')].find(x=>x.textContent==='CASH SELLING').click()});await p.waitForTimeout(80);
obs.shorts_inner=await p.evaluate(()=>document.querySelector('#p-patterns > .subview:not([hidden]) .subview:not([hidden])')?.dataset.sub);
// --- calls
await tab('CALL LIBRARY');obs.calls_sub_default=await p.evaluate(()=>document.querySelector('#p-calls > .subview:not([hidden])').dataset.sub);
await p.evaluate(()=>{[...document.querySelectorAll('#p-calls > .subtabs .subtab')].find(x=>/UPCOMING/.test(x.textContent)).click()});await p.waitForTimeout(200);
obs.calls_sub_after=await p.evaluate(()=>document.querySelector('#p-calls > .subview:not([hidden])').dataset.sub);obs.ur_count=await p.evaluate(()=>document.getElementById('ur-count')?.textContent);
await p.evaluate(()=>{const q=document.getElementById('ur-q');q.value='AB';q.dispatchEvent(new Event('input'))});await p.waitForTimeout(150);obs.ur_count_filtered=await p.evaluate(()=>document.getElementById('ur-count')?.textContent);
await click('#p-calls .urchip',1);obs.ur_count_chip=await p.evaluate(()=>document.getElementById('ur-count')?.textContent);
// --- exchange
await tab('EXCHANGE TRACKER');obs.ex_group_default=await p.evaluate(()=>[...document.querySelectorAll('.exchangegroup')].find(g=>!g.hidden).dataset.exchangeGroup);
await click('.exswitchbtn',1);obs.ex_group_after=await p.evaluate(()=>[...document.querySelectorAll('.exchangegroup')].find(g=>!g.hidden).dataset.exchangeGroup);
await click('.exswitchbtn',0);await click('.exrbtn',1);obs.ex_range=await p.evaluate(()=>[...document.querySelectorAll('.exchangegroup:not([hidden]) .exrange')].find(r=>!r.hidden)?.dataset.xr);
await p.evaluate(()=>{const c=document.querySelector('.exchangegroup:not([hidden]) .exwd');c.querySelector('.wdsel').value='Monday';c.querySelector('.wdsel').dispatchEvent(new Event('change'));c.querySelector('.wdper').value='all';c.querySelector('.wdper').dispatchEvent(new Event('change'))});
obs.ex_wd=await p.evaluate(()=>{const v=[...document.querySelectorAll('.exchangegroup:not([hidden]) .wdview')].find(x=>!x.hidden);return v&&v.dataset.wd+'/'+v.dataset.wp});
// --- stocks + watchlist + peer radar
await tab('STOCKS');await p.evaluate(()=>{location.hash='CUB';cur='CUB';draw()});await p.waitForTimeout(300);
obs.stk_chart_nodes=await p.evaluate(()=>document.getElementById('ch').childNodes.length>20);obs.stk_pattern_cards=await p.evaluate(()=>document.querySelectorAll('#insights .ptpanel').length);obs.stk_flags=await p.evaluate(()=>[...document.querySelectorAll('#screens-row .scrchip')].map(x=>x.textContent.trim()).join('|'));
obs.stk_header=await p.evaluate(()=>document.querySelector('#sh .px')?.textContent);obs.stk_oi_panel=await p.evaluate(()=>document.getElementById('oich').childNodes.length>5);
obs.stk_rat=await p.evaluate(()=>{const S=D.stocks.CUB;return [S.rat.filter(v=>v!=null).length,+S.rat[S.rat.length-1].toFixed(3),S.d.filter(v=>v===1).length]});
obs.stk_ohl=await p.evaluate(()=>{const S=D.stocks.CUB,i=S.c.length-1;return [S.c[i],S.o[i],S.h[i],S.l[i]]});
await p.evaluate(()=>{toggleWL('CUB');toggleWL('SUPREMEIND')});await p.waitForTimeout(100);
await p.evaluate(()=>{[...document.querySelectorAll('.subtab')].find(x=>x.dataset.sub==='watch').click()});await p.waitForTimeout(200);
obs.wl_rows=await p.evaluate(()=>[...document.querySelectorAll('#wl-body tbody tr')].map(r=>r.children[0].textContent+':'+r.children[1].textContent));
await tab('TECHNICAL PATTERNS');obs.pt_wlline_after=await p.evaluate(()=>document.getElementById('pt-wl')?.innerText.slice(0,140)||'');
const sym=await p.evaluate(()=>ALL.find(k=>(D.stocks[k].fl||[]).some(f=>f.g==='short')));obs.jump_stock=sym;
await tab('STOCKS');await p.evaluate(()=>{document.querySelector('.subtab[data-sub="chart"]').click()});await p.evaluate(s=>{location.hash=s;cur=s;draw()},sym);await p.waitForTimeout(300);
await p.evaluate(()=>{[...document.querySelectorAll('#screens-row .scrchip')].find(x=>/SHORT IDEAS/.test(x.textContent)).click()});await p.waitForTimeout(300);
obs.jump=await p.evaluate(()=>({tab:document.querySelector('.tab.on').textContent,sub:document.querySelector('#p-patterns > .subview:not([hidden])').dataset.sub,inner:(document.querySelector('#p-patterns > .subview:not([hidden]) .subtab.on')||{}).textContent}));
obs.errors=errs;
fs.writeFileSync(process.env.OUT,JSON.stringify(obs,null,1));console.log('wrote',process.env.OUT,'errors:',errs.length);await b.close()})()
