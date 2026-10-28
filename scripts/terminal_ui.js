// BEGIN TERMINAL UI
const terminalPrefs={ready:false,previousView:null,commandIndex:0,commandMarkets:[],lastFocus:null};
function terminalSafeRead(key,fallback){try{return localStorage.getItem(key)||fallback}catch{return fallback}}
function terminalSave(key,value){try{localStorage.setItem(key,value)}catch{}}
function closeInspector(){document.body.classList.remove('inspector-open');$('#research-detail')?.setAttribute('aria-hidden','true')}
function terminalInspector(){
 const target=$('#research-detail');if(!target)return;
 target.classList.add('terminal-inspector');target.setAttribute('role','complementary');target.setAttribute('aria-label','品种证据面板');target.setAttribute('aria-hidden',document.body.classList.contains('inspector-open')?'false':'true');
 if(!target.querySelector('.inspector-controls'))target.insertAdjacentHTML('afterbegin','<div class="inspector-controls"><span>INSTRUMENT / EVIDENCE</span><div><button id="inspector-price" class="tool-button">查看价格图 ↗</button><button id="inspector-close" class="icon-button" aria-label="关闭证据面板">×</button></div></div>');
 $('#inspector-close').onclick=closeInspector;
 $('#inspector-price').onclick=()=>{closeInspector();location.hash='overview';setTimeout(()=>$('#detail')?.scrollIntoView({behavior:'smooth',block:'start'}),60)};
}
selectResearch=function(code){
 state.selected=code;$('#research-detail').innerHTML=researchDetail();bindResearchDetail();researchTable();scatter();terminalInspector();document.body.classList.add('inspector-open');$('#research-detail').setAttribute('aria-hidden','false');
};
function terminalJump(code){closeCommand();state.selected=code;if(state.view==='research')selectResearch(code);else{location.hash='research';setTimeout(()=>{if($('#research-detail'))selectResearch(code)},60)}}
function openCommand(){
 terminalPrefs.lastFocus=document.activeElement;$('#command-menu').hidden=false;$('#command-input').value='';terminalPrefs.commandIndex=0;terminalCommandResults();$('#command-input').focus();
}
function closeCommand(){$('#command-menu').hidden=true;terminalPrefs.lastFocus?.focus?.()}
function terminalCommandResults(){
 const q=$('#command-input').value.trim().toLowerCase();const ms=DATA.markets.filter(m=>`${m.name} ${m.code} ${m.main.contract} ${m.exchange}`.toLowerCase().includes(q)).slice(0,12);terminalPrefs.commandMarkets=ms;terminalPrefs.commandIndex=Math.max(0,Math.min(terminalPrefs.commandIndex,ms.length-1));
 $('#command-results').innerHTML=ms.length?ms.map((m,i)=>`<button role="option" aria-selected="${i===terminalPrefs.commandIndex}" class="command-result ${i===terminalPrefs.commandIndex?'active':''}" data-command-code="${m.code}"><span class="command-symbol">${m.code.toUpperCase()}</span><span class="command-market">${m.name}<small>${m.main.contract.toUpperCase()} · ${m.exchange}</small></span><span class="command-metric ${color(m.analysis?.return20)}">${factorPct(m.analysis?.return20)}<small>20 日收益</small></span><span class="command-enter">↵</span></button>`).join(''):'<div class="empty">没有匹配的品种。</div>';
 $$('[data-command-code]').forEach(b=>b.onclick=()=>terminalJump(b.dataset.commandCode));
}
function terminalInit(){
 if(terminalPrefs.ready)return;terminalPrefs.ready=true;
 const root=document.documentElement;root.dataset.theme=terminalSafeRead('guanlan-theme','dark');root.dataset.density=terminalSafeRead('guanlan-density','compact');
 document.body.classList.toggle('rail-collapsed',terminalSafeRead('guanlan-rail','expanded')==='collapsed');
 const theme=()=>{$('#theme-toggle').textContent=root.dataset.theme==='dark'?'浅色':'深色';$('#theme-toggle').setAttribute('aria-label',root.dataset.theme==='dark'?'切换为浅色主题':'切换为深色主题')};
 const density=()=>{$('#density-toggle').textContent=root.dataset.density==='compact'?'紧凑':'舒展';$('#density-toggle').setAttribute('aria-label','切换信息密度，当前'+$('#density-toggle').textContent)};
 theme();density();$('#theme-toggle').onclick=()=>{root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';terminalSave('guanlan-theme',root.dataset.theme);theme()};
 $('#density-toggle').onclick=()=>{root.dataset.density=root.dataset.density==='compact'?'comfortable':'compact';terminalSave('guanlan-density',root.dataset.density);density()};
 $('#nav-toggle').onclick=()=>{const c=document.body.classList.toggle('rail-collapsed');terminalSave('guanlan-rail',c?'collapsed':'expanded');$('#nav-toggle').setAttribute('aria-label',c?'展开侧边导航':'收起侧边导航')};
 $('#command-open').onclick=openCommand;$('#command-close').onclick=closeCommand;$('#command-menu').onclick=e=>{if(e.target===$('#command-menu'))closeCommand()};
 $('#command-input').oninput=()=>{terminalPrefs.commandIndex=0;terminalCommandResults()};
 $('#command-input').onkeydown=e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();const n=terminalPrefs.commandMarkets.length;if(n){terminalPrefs.commandIndex=(terminalPrefs.commandIndex+(e.key==='ArrowDown'?1:n-1))%n;terminalCommandResults();$('#command-results .active')?.scrollIntoView({block:'nearest'})}}else if(e.key==='Enter'){e.preventDefault();const m=terminalPrefs.commandMarkets[terminalPrefs.commandIndex];if(m)terminalJump(m.code)}};
 document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommand()}if(e.key==='Escape'){if(!$('#command-menu').hidden)closeCommand();else closeInspector()}});
}
function terminalMatrix(){
 const header=$('#research-table-title');if(!header||header.closest('.matrix-workspace'))return;
 const toolbar=header.nextElementSibling,panel=toolbar?.nextElementSibling,stats=$('#app .stats-grid');if(!toolbar||!panel||!stats)return;
 const section=document.createElement('section');section.className='matrix-workspace';stats.insertAdjacentElement('afterend',section);section.append(header,toolbar,panel);
 const table=section.querySelector('table');if(table)table.setAttribute('aria-label','横截面研究矩阵');
 const detail=$('#research-detail');if(detail)detail.classList.add('terminal-inspector');
 const methods=$('#research-method');if(methods&&!methods.closest('details')){const fold=document.createElement('details');fold.className='terminal-methods';fold.innerHTML='<summary><span>指标定义与判定规则</span><small>收益口径 / 价仓联动 / 席位边界</small><span>＋</span></summary>';methods.insertAdjacentElement('beforebegin',fold);fold.append(methods)}
 if($('#jump-research-method'))$('#jump-research-method').onclick=e=>{e.preventDefault();const fold=$('#research-method').closest('details');if(fold)fold.open=true;$('#research-method').scrollIntoView({behavior:'smooth',block:'start'})};
}
const terminalHeadingBase=heading;
heading=function(title,sub,kicker){const titles={research:'研究雷达',overview:'市场概览',trends:'趋势全景',positions:'持仓结构',sources:'数据与方法'};const subs={research:'横截面强弱、量价参与度与席位证据',overview:'收盘价格、成交与持仓变化',trends:'固定合约趋势状态与跨品种比较',positions:'会员排名、样本差与持仓集中度',sources:'数据覆盖、计算口径与可用性'};return terminalHeadingBase(titles[state.view]||title,subs[state.view]||sub,kicker)};
function terminalSync(){
 terminalInit();if(terminalPrefs.previousView!==state.view)closeInspector();terminalPrefs.previousView=state.view;
 $('#side-date').textContent=DATA.asOf;$('#terminal-date').textContent=DATA.asOf+' / 收盘';$('#terminal-date').title='数据快照日期 '+DATA.asOf+'，非实时行情';
 const ribbon=$('#market-ribbon');ribbon.innerHTML=['au','cu','rb','sc','m','ta','lc','i'].map(c=>DATA.markets.find(m=>m.code===c)).filter(Boolean).map(m=>`<button class="ribbon-quote" data-ribbon-code="${m.code}" aria-label="查看${m.name}证据"><span>${m.name}</span><b>${num(m.main.close,decimals(m))}</b><em class="${color(m.main.changePct)}">${signed(m.main.changePct,2)}%</em></button>`).join('');$$('[data-ribbon-code]').forEach(b=>b.onclick=()=>terminalJump(b.dataset.ribbonCode));
 $('#app').dataset.view=state.view;$('#export').innerHTML='<span>↓</span> '+(state.view==='research'?'导出研究':'导出数据');
 if(state.view==='research'){terminalMatrix();terminalInspector()}
 $$('nav [data-view]').forEach(a=>a.setAttribute('aria-current',a.dataset.view===state.view?'page':'false'));
}
const terminalRenderBase=render;
render=function(){terminalRenderBase();terminalSync()};
// END TERMINAL UI
