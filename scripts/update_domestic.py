"""Build a dated SHFE/INE public EOD snapshot. Run: python scripts/update_domestic.py

Raw responses are cached locally. Published data never falls back to fabricated values.
"""
import argparse, concurrent.futures, datetime as dt, json, pathlib, urllib.request, urllib.error, time
ROOT=pathlib.Path(__file__).resolve().parents[1]
CACHE=ROOT/'data'/'raw'; CACHE.mkdir(parents=True,exist_ok=True)
META={
 'cu':('沪铜','有色金属','元/吨'),'al':('沪铝','有色金属','元/吨'),'zn':('沪锌','有色金属','元/吨'),
 'pb':('沪铅','有色金属','元/吨'),'ni':('沪镍','有色金属','元/吨'),'sn':('沪锡','有色金属','元/吨'),
 'ao':('氧化铝','有色金属','元/吨'),'ad':('铸造铝合金','有色金属','元/吨'),
 'bc':('国际铜','有色金属','元/吨'),'au':('沪金','贵金属','元/克'),'ag':('沪银','贵金属','元/千克'),
 'rb':('螺纹钢','黑色金属','元/吨'),'hc':('热轧卷板','黑色金属','元/吨'),'ss':('不锈钢','黑色金属','元/吨'),
 'wr':('线材','黑色金属','元/吨'),'sc':('原油','能源化工','元/桶'),'lu':('低硫燃料油','能源化工','元/吨'),
 'fu':('燃料油','能源化工','元/吨'),'bu':('沥青','能源化工','元/吨'),'ru':('天然橡胶','能源化工','元/吨'),
 'nr':('20号胶','能源化工','元/吨'),'br':('丁二烯橡胶','能源化工','元/吨'),'sp':('纸浆','能源化工','元/吨'),
 'op':('胶版印刷纸','能源化工','元/吨'),'ec':('集运欧线','航运','点')}
def number(v):
    try: return float(str(v).replace(',',''))
    except (ValueError,TypeError): return None
def fetch(kind,day):
    ymd=day.strftime('%Y%m%d'); key=f'{kind}{ymd}.dat'; path=CACHE/key
    url='https://www.shfe.com.cn/data/tradedata/future/dailydata/'+key
    try:
        if path.exists(): raw=path.read_bytes()
        else:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'GuanlanResearch/1.0'}),timeout=18) as r: raw=r.read()
        doc=json.loads(raw)
        if doc.get('report_date')!=ymd: return {'date':day.isoformat(),'error':'date mismatch','url':url}
        rows=doc.get('o_curinstrument' if kind=='kx' else 'o_cursor',[])
        if not rows: return {'date':day.isoformat(),'error':'no published records','url':url}
        path.write_bytes(raw)
        return {'date':day.isoformat(),'rows':rows,'url':url,'updated':doc.get('update_date')}
    except Exception as e: return {'date':day.isoformat(),'error':str(e),'url':url}
def parse_rows(doc):
    out=[]
    for r in doc['rows']:
        code=r.get('PRODUCTGROUPID','').strip(); month=str(r.get('DELIVERYMONTH','')).strip()
        if code not in META or not month.isdigit() or len(month)!=4 or str(r.get('PRODUCTCLASS'))!='1': continue
        row={'code':code,'contract':code+month,'date':doc['date']}
        for k,f in [('open','OPENPRICE'),('high','HIGHESTPRICE'),('low','LOWESTPRICE'),('close','CLOSEPRICE'),('settle','SETTLEMENTPRICE'),('prevSettle','PRESETTLEMENTPRICE'),('volume','VOLUME'),('oi','OPENINTEREST'),('oiChange','OPENINTERESTCHG'),('turnover','TURNOVER')]: row[k]=number(r.get(f))
        if row['close'] is not None and row['close']<=0: row['close']=None
        if row['prevSettle'] and row['close']: row['changePct']=(row['close']/row['prevSettle']-1)*100
        else: row['changePct']=None
        out.append(row)
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--as-of'); p.add_argument('--start'); args=p.parse_args()
    asof=dt.date.fromisoformat(args.as_of) if args.as_of else dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()-dt.timedelta(days=1)
    start=dt.date.fromisoformat(args.start) if args.start else asof-dt.timedelta(days=99)
    days=[asof-dt.timedelta(days=i) for i in range((asof-start).days+1) if (asof-dt.timedelta(days=i)).weekday()<5]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(lambda d:fetch('kx',d),days))
    good=sorted((r for r in results if 'rows' in r),key=lambda x:x['date'])
    if not good: raise RuntimeError('No valid official EOD files; existing snapshot preserved.')
    latest=good[-1]; date=latest['date']; parsed={r['date']:parse_rows(r) for r in good}; current=parsed[date]
    if date!=asof.isoformat(): raise RuntimeError(f'SHFE latest report {date} differs from requested {asof}; existing snapshot preserved.')
    ranks=fetch('pm',dt.date.fromisoformat(date)); markets=[]
    for code,(name,sector,unit) in META.items():
        contracts=sorted([r for r in current if r['code']==code],key=lambda r:r['oi'] or 0,reverse=True)
        if not contracts: continue
        valid=[r for r in contracts if r['close'] is not None and (r['volume'] or 0)>0]
        if not valid: continue
        main=valid[0]; history=[r for day in sorted(parsed) for r in parsed[day] if r['contract']==main['contract'] and r['close'] is not None]
        rank=[]
        if 'rows' in ranks:
            for r in ranks['rows']:
                if r.get('INSTRUMENTID','').strip()==main['contract'] and 1<=int(r.get('RANK',-1))<=20:
                    rank.append({'rank':int(r['RANK']),'longName':r.get('PARTICIPANTABBR2','').strip(),'long':number(r.get('CJ2')),'longChange':number(r.get('CJ2_CHG')),'shortName':r.get('PARTICIPANTABBR3','').strip(),'short':number(r.get('CJ3')),'shortChange':number(r.get('CJ3_CHG'))})
        markets.append({'code':code,'name':name,'sector':sector,'unit':unit,'exchange':'INE' if code in ('sc','lu','nr','bc','ec') else 'SHFE','main':main,'history':history,'contracts':contracts,'ranks':sorted(rank,key=lambda r:r['rank']),'totalVolume':sum(r['volume'] or 0 for r in contracts),'totalOi':sum(r['oi'] or 0 for r in contracts),'totalOiChange':sum(r['oiChange'] or 0 for r in contracts)})
    data={'schema':'domestic-v1','asOf':date,'fetchedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'sourceUpdated':latest.get('updated'),'sources':{'quotes':latest['url'],'ranks':ranks['url'],'landing':'https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/'},'coverage':{'exchanges':['SHFE','INE'],'firstDate':good[0]['date'],'tradingDays':len(good),'unavailableDates':[{'date':r['date'],'reason':r['error']} for r in results if 'error' in r],'rankingError':ranks.get('error')},'markets':markets}
    assert markets and all(m['main']['date']==date and m['history'][-1]['date']==date for m in markets)
    dest=ROOT/'dist'/'data.json'; tmp=dest.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); tmp.replace(dest)
    print(json.dumps({'asOf':date,'markets':len(markets),'tradingDays':len(good),'rankingMarkets':sum(bool(m['ranks']) for m in markets),'unavailableDates':len(data['coverage']['unavailableDates'])}))
