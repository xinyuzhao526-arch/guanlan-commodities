"""Merge independently validated exchange snapshots. Never substitute missing values."""
import collections, datetime as dt, json, pathlib, urllib.parse
ROOT=pathlib.Path(__file__).resolve().parents[1]
NAMES={'SHFE':'上期所','INE':'上期能源','DCE':'大商所','CZCE':'郑商所','GFEX':'广期所'}

def validate(m, day):
    assert m['main']['date']==day, (m['code'],'snapshot date mismatch')
    assert m['main']['close'] is not None and m['main']['close']>0, m['code']
    assert len({h['date'] for h in m['history']})==len(m['history']),m['code']
    assert all(h['date']<=day and h['close'] is not None and h['close']>0 for h in m['history']),m['code']
    assert m.get('quoteSource',{}).get('url'),m['code']
    assert all(r.get('long') is None or r['long']>=0 for r in m['ranks']),m['code']
    assert all(r.get('short') is None or r['short']>=0 for r in m['ranks']),m['code']
    if m['main'].get('prevSettle') and m['main'].get('changePct') is not None:
        expect=(m['main']['close']/m['main']['prevSettle']-1)*100
        assert abs(m['main']['changePct']-expect)<0.015,(m['code'],'return basis mismatch')

if __name__=='__main__':
    path=ROOT/'dist/data.json'
    current=json.loads(path.read_text(encoding='utf-8'))
    archive=ROOT/'data/shfe-base.json'
    if not archive.exists() or all(m['exchange'] in ('SHFE','INE') for m in current['markets']):
        archive.write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8')
    base=json.loads(archive.read_text(encoding='utf-8')); day=base['asOf']; markets=[]
    for m in base['markets']:
        m['quoteSource']={'name':'上期所官方日交易快讯','url':base['sources']['quotes'],'date':day,'official':True}
        m['rankSource']={'name':'上期所官方会员持仓排名','url':base['sources']['ranks'],'date':day,'official':True}
        m['historySource']={'name':'上期所官方固定合约日行情','url':base['sources']['landing']}
        m['historyType']='fixed-contract';m['aggregateScope']='all-contracts';m['changeBasis']='previous-settlement'
        markets.append(m)
    sources=[{'exchange':x,'name':NAMES[x],'quoteStatus':'已接入','rankingStatus':'已接入（部分合约未取得）','official':True,'url':base['sources']['landing'],'quoteUrl':base['sources']['quotes'],'rankUrl':base['sources']['ranks'],'date':day,'marketCount':sum(m['exchange']==x for m in markets)} for x in ('SHFE','INE')]
    for ex in ('dce','czce','gfex'):
        f=ROOT/'data'/f'{ex}-markets.json'
        if not f.exists():
            sources.append({'exchange':ex.upper(),'name':NAMES[ex.upper()],'quoteStatus':'尚未取得','rankingStatus':'尚未取得','official':False,'marketCount':0,'date':day})
            continue
        packet=json.loads(f.read_text(encoding='utf-8'))
        batch=packet if isinstance(packet,list) else packet.get('markets',[])
        for m in batch:
            m.setdefault('historyType','fixed-contract');m.setdefault('aggregateScope','all-contracts')
            m.setdefault('changeBasis','previous-settlement' if m['main'].get('prevSettle') else 'unavailable')
            m.setdefault('rankingNote',m.get('rankUnavailableReason',''))
            if ex=='gfex' and m['code'] in ('pt','pd') and not m['ranks']:
                reason=next((r['reason'] for r in packet.get('coverage',{}).get('rankingErrors',[]) if r['code']==m['code']),None)
                m['rankingNote']=('广期所当日排名接口返回：查询的合约号成交量不能小于 20000；因此未取得该合约排名。' if reason and '20000' in reason else '本次未取得广期所该合约当日排名。'+(reason or ''))
            for field in ('quoteSource','rankSource'):
                if m.get(field,{}).get('url'):
                    hostname=urllib.parse.urlsplit(m[field]['url']).hostname
                    if hostname in ('www.czce.com.cn','www.gfex.com.cn','www.shfe.com.cn','www.ine.cn'):
                        m[field]['official']=True
            m['history']=sorted(m.get('history',[]),key=lambda h:h['date'])
            validate(m,day);markets.append(m)
        source=packet.get('sourceStatus',{}) if isinstance(packet,dict) else {}
        if not isinstance(source,dict): source={'note':str(source)}
        if ex=='dce':
            snap_count=sum(m['main'].get('dataOrigin')=='dated-after-close-quote-snapshot' for m in batch)
            matched=sum(bool(m.get('mainMatchedContinuous')) for m in batch)
            source['note']=f'大商所官方日行情及会员排名接口本次未取得可用数据。新浪来源中 {snap_count} 个代表合约取当日15:00后的盘后快照，并核对昨收、昨结算与前一交易日日线；{matched} 个与当日主力连续行情匹配。仅代表合约口径，不混入全合约汇总。会员排名仍缺失。'
        elif ex=='czce':
            source['note']='官方日行情与会员排名。排除当日无成交、无有效收盘的品种；菜籽代表合约历史有效收盘较少，不以结算价补收盘。'
        elif ex=='gfex':
            missing='、'.join(m['name'] for m in batch if not m['ranks'])
            source['note']=f'官方全合约日行情已接入，{sum(bool(m["ranks"]) for m in batch)}/{len(batch)} 个代表合约取得会员排名。'+(f'{missing} 排名未取得，具体原因见各合约说明。' if missing else '')
        first=batch[0] if batch else {}
        source={k:v for k,v in source.items() if k not in ('exchange','marketCount','date','official')}
        sources.append({'exchange':ex.upper(),'name':NAMES[ex.upper()],'quoteStatus':'已接入' if batch else '尚未取得','rankingStatus':f"{sum(bool(m['ranks']) for m in batch)} / {len(batch)} 个品种" if batch else '尚未取得','official':first.get('quoteSource',{}).get('official',False),'marketCount':len(batch),'date':day,'url':first.get('quoteSource',{}).get('url'),'quoteUrl':first.get('quoteSource',{}).get('url'),'rankUrl':first.get('rankSource',{}).get('url'),**source})
    for m in markets: validate(m,day)
    assert len({m['code'] for m in markets})==len(markets),'Duplicate product code'
    base.update({'markets':markets,'exchangeSources':sources,'fetchedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'version':'multi-exchange-v2'})
    base['coverage']['exchanges']=[s['exchange'] for s in sources if s['marketCount']]
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(base,ensure_ascii=False,separators=(',',':')),encoding='utf-8');tmp.replace(path)
    print(json.dumps({'asOf':day,'markets':len(markets),'byExchange':dict(collections.Counter(m['exchange'] for m in markets)),'rankingMarkets':sum(bool(m['ranks']) for m in markets)},ensure_ascii=False))
