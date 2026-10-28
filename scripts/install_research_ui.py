"""Insert the maintained research view into the buildless dashboard."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'dist/app.js';s=p.read_text(encoding='utf-8')
ui=(ROOT/'scripts/research_ui.js').read_text(encoding='utf-8')
if '// BEGIN RESEARCH UI' in s:
    a=s.index('// BEGIN RESEARCH UI');b=s.index('// END RESEARCH UI',a)+len('// END RESEARCH UI');s=s[:a]+ui+s[b:]
else:s=s.replace('function render(){',ui+'\nfunction render(){')
s=s.replace("const state={view:'overview',", "const state={view:'research',rSearch:'',rFilter:'全部',rSector:'',rSort:'strengthPercentile20',rOrder:-1,")
s=s.replace('const views={overview,trends,positions,sources},names={overview:',"const views={research,overview,trends,positions,sources},names={research:'研究雷达',overview:")
s=s.replace("location.hash.slice(1):'overview'", "location.hash.slice(1):'research'")
s=s.replace("$('#export').onclick=exportCsv;", "$('#export').onclick=state.view==='research'?exportResearch:exportCsv;")
if 'if(m.analysis){const a=m.analysis' not in s:
    s=s.replace('function trend(m){',"function trend(m){if(m.analysis){const a=m.analysis;return {id:a.trendDirection===1?'bull':a.trendDirection===-1?'bear':a.trendDirection===0?'mixed':'unknown',name:a.trendLabel,class:a.trendDirection===1?'positive':a.trendDirection===-1?'negative':'',ma5:a.ma5,ma20:a.ma20}}")
s=s.replace("ma5:idx>=4?mean(all.slice(idx-4,idx+1).map(v=>v.close)):null,ma20:idx>=19?mean(all.slice(idx-19,idx+1).map(v=>v.close)):null", "ma5:priceMeanAt(m,v.date,5),ma20:priceMeanAt(m,v.date,20)")
s=s.replace('近 24 日','近 24 样本')
if "bindSelection();if(state.view==='research')" not in s:s=s.replace("chart();bindSelection();", "chart();bindSelection();if(state.view==='research')bindResearch();")
p.write_text(s,encoding='utf-8')
p=ROOT/'dist/index.html';s=p.read_text(encoding='utf-8')
if 'data-view="research"' not in s:
    s=s.replace('<span class="nav-dot"></span>','')
    s=s.replace('<nav aria-label="主导航">','<nav aria-label="主导航"><a href="#research" data-view="research"><span>◎</span>研究雷达<span class="nav-dot"></span></a>')
    s=s.replace('class="brand" href="#overview"','class="brand" href="#research"')
    s=s.replace('id="breadcrumb">市场概览','id="breadcrumb">研究雷达')
    s=s.replace('多交易所版 · 来源可追溯','多维研究版 · 证据可追溯')
p.write_text(s,encoding='utf-8')
print('Research view installed.')
