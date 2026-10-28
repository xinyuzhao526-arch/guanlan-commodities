"""DCE coverage from publicly readable Sina daily bars, honestly labelled.

No credentials, terminal data, or guessed exchange totals. Fixed delivery
contracts only; continuous series are used solely to check the as-of main.
Run: python scripts/source_dce.py --as-of 2026-10-21 --start 2026-07-14
"""
import argparse
import concurrent.futures
import datetime as dt
import json
from pathlib import Path
import re
import time
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw' / 'dce-sina'
DAILY = 'https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_=/InnerFuturesNewService.getDailyKLine?symbol='
LIST = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQFuturesData?page=1&num=100&sort=position&asc=0&node={}&base=futures'
# Code, name, display sector, Sina public product node, price unit.
PRODUCTS = [
 ('i','铁矿石','黑色建材','tks_qh','元/吨'),
 ('j','焦炭','黑色建材','jt_qh','元/吨'),
 ('jm','焦煤','黑色建材','jm_qh','元/吨'),
 ('m','豆粕','农产品','dp_qh','元/吨'),
 ('y','豆油','农产品','dy_qh','元/吨'),
 ('p','棕榈油','农产品','zly_qh','元/吨'),
 ('a','豆一','农产品','dd_qh','元/吨'),
 ('b','豆二','农产品','de_qh','元/吨'),
 ('c','玉米','农产品','hym_qh','元/吨'),
 ('cs','玉米淀粉','农产品','ymdf_qh','元/吨'),
 ('jd','鸡蛋','农产品','jd_qh','元/500千克'),
 ('lh','生猪','农产品','lh_qh','元/吨'),
 ('l','聚乙烯','能源化工','lldpe_qh','元/吨'),
 ('v','PVC','能源化工','pvc_qh','元/吨'),
 ('pp','聚丙烯','能源化工','jbx_qh','元/吨'),
 ('eg','乙二醇','能源化工','yec_qh','元/吨'),
 ('eb','苯乙烯','能源化工','byx_qh','元/吨'),
 ('pg','液化石油气','能源化工','pg_qh','元/吨'),
 ('rr','粳米','农产品','gm_qh','元/吨'),
 ('lg','原木','黑色建材','lg_qh','元/立方米'),
 ('bz','纯苯','能源化工','bz_qh','元/吨'),
]

def get(url, cache_name, refresh=False):
    path = RAW / cache_name
    if path.exists() and not refresh:
        return path.read_text(encoding='utf-8')
    error = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=(10, 25), headers={
                'Referer':'https://finance.sina.com.cn/', 'User-Agent':'Mozilla/5.0'})
            r.raise_for_status()
            text = r.content.decode('utf-8', errors='replace')
            path.write_text(text, encoding='utf-8')
            return text
        except requests.RequestException as exc:
            error = exc
            time.sleep(.5 * (attempt+1))
    raise error

def daily(symbol, refresh):
    text = get(DAILY+symbol, symbol+'.jsonp', refresh)
    match = re.search(r'=\s*\((\[.*\])\)\s*;', text, re.S)
    if not match:
        raise ValueError('Invalid Sina JSONP for '+symbol)
    rows = json.loads(match.group(1))
    if not isinstance(rows, list):
        raise ValueError('No daily bars for '+symbol)
    return rows

def number(value):
    try:
        return float(value) if value not in (None, '') else None
    except (ValueError, TypeError):
        return None

def probe_official(as_of):
    """Record actual responses; these are not used as successful data sources."""
    urls = [
      'http://www.dce.com.cn/dceapi/forward/publicweb/dailystat/dayQuotes',
      'http://www.dce.com.cn/publicweb/quotesdata/dayQuotesCh.html',
      'http://www.dce.com.cn/publicweb/quotesdata/exportMemberDealPosiQuotesBatchData.html',
    ]
    results = []
    date=dt.date.fromisoformat(as_of)
    for index,url in enumerate(urls):
        try:
            if index==0:
                parameters={'tradeDate':as_of.replace('-',''),'tradeType':'0','variety':'all'}
                r=requests.post(url,json=parameters,timeout=(5,10))
            else:
                parameters={'year':date.year,'month':date.month-1,'day':date.day,
                            'dayQuotes.variety':'all','dayQuotes.trade_type':'0'}
                if index==2:
                    parameters.update({'memberDealPosiQuotes.variety':'m',
                                       'memberDealPosiQuotes.trade_type':'0',
                                       'contract.contract_id':'m2701'})
                r=requests.get(url,params=parameters,timeout=(5,10))
            r.encoding='utf-8'
            results.append({'url':url,'requestedDate':as_of,'parameters':parameters,'httpStatus':r.status_code,
                            'responseExcerpt':r.text[:250]})
        except requests.RequestException as exc:
            results.append({'url':url,'error':str(exc)[:250]})
    return results

def fetch_product(product, args):
    code,name,sector,node,unit=product
    listings=json.loads(get(LIST.format(node), code+'-contracts.json', args.refresh))
    fixed=[q for q in listings if re.fullmatch(code.upper()+r'\d{4}',q['symbol'])]
    fixed.sort(key=lambda q:number(q.get('position')) or -1, reverse=True)
    if not fixed:
        raise ValueError(code+': no fixed contract listed')
    # The current snapshot supplies candidates only, never 21 Oct prices.
    continuous={q['d']:q for q in daily(code.upper()+'0', args.refresh)}
    target=continuous.get(args.as_of)
    candidates=[]
    chosen=None
    matched=False
    for quote in fixed[:2]:
        symbol=quote['symbol']
        bars=daily(symbol,args.refresh)
        bars=sorted((r for r in bars if r['d']<=args.as_of),key=lambda r:r['d'])
        # Daily history can be published after the after-close quote table.
        # Append a separately labelled, dated close snapshot only after 15:00.
        if bars and bars[-1]['d']<args.as_of and quote.get('tradedate')==args.as_of and '15:00:00'<=str(quote.get('ticktime',''))<'21:00:00':
            prior=bars[-1]
            if number(quote.get('presettlement'))!=number(prior.get('s')) or number(quote.get('preclose'))!=number(prior.get('c')):
                raise ValueError(code+': current snapshot previous settlement/close does not match the last daily bar')
            fields={'o':'open','h':'high','l':'low','c':'close','v':'volume','p':'position','s':'settlement'}
            snapshot={'d':args.as_of,**{k:quote.get(v) for k,v in fields.items()},'_afterCloseSnapshot':True,'_ticktime':quote.get('ticktime')}
            if any(number(snapshot.get(k)) is None for k in fields):
                raise ValueError(code+': after-close snapshot has missing fields')
            if not 0<number(snapshot['l'])<=number(snapshot['c'])<=number(snapshot['h']) or number(snapshot['v'])<=0 or number(snapshot['p'])<0:
                raise ValueError(code+': invalid after-close snapshot OHLC/volume/OI')
            bars.append(snapshot)
        if not bars or bars[-1]['d']!=args.as_of:
            continue
        last=bars[-1]
        candidates.append((quote,bars))
        if target and all(number(last.get(k))==number(target.get(k))
                          for k in ('o','h','l','c','v','p')):
            chosen=(quote,bars)
            matched=True
            break
    if chosen is None:
        if not candidates:
            raise ValueError(code+': no as-of quote from concrete contracts')
        chosen=max(candidates,key=lambda qb:number(qb[1][-1].get('p')) or -1)
    quote,bars=chosen
    symbol=quote['symbol']
    from_snapshot=bool(bars[-1].get('_afterCloseSnapshot'))
    history=[]
    previous=None
    for raw in bars:
        settle=number(raw.get('s'))
        if settle is not None and settle<=0:
            settle=None
        prev_settle=number(previous.get('s')) if previous else None
        if prev_settle is not None and prev_settle<=0:
            prev_settle=None
        close=number(raw.get('c'))
        oi=number(raw.get('p'))
        prev_oi=number(previous.get('p')) if previous else None
        row={'code':code,'contract':symbol.lower(),'date':raw['d'],
             'open':number(raw.get('o')),'high':number(raw.get('h')),
             'low':number(raw.get('l')),'close':close,'settle':settle,
             'prevSettle':prev_settle,'volume':number(raw.get('v')),'oi':oi,
             'oiChange':oi-prev_oi if oi is not None and prev_oi is not None else None,
             'turnover':None,
             'changePct':(close/prev_settle-1)*100 if close is not None and prev_settle else None,
             'changeBasis':'previous-trading-day-settlement',
             'oiChangeMethod':'same-contract previous available trading-day open-interest difference'}
        if raw.get('_afterCloseSnapshot'):
            row['dataOrigin']='dated-after-close-quote-snapshot';row['quoteTime']=raw['_ticktime']
        if raw['d']>=args.start:
            history.append(row)
        previous=raw
    if len(history)<20:
        raise ValueError(code+': fewer than 20 as-of historical bars')
    main=history[-1]
    validations=[]
    if from_snapshot:
        validations.append({'snapshotDate':args.as_of,'snapshotTime':quote.get('ticktime'),
          'previousSettlementMatchesHistoricalBar':main['prevSettle']==number(quote.get('presettlement')),
          'previousCloseMatchesHistoricalBar':number(bars[-2].get('c'))==number(quote.get('preclose')),
          'note':'Current dated quote snapshot after 15:00; daily history has not yet published the current bar.'})
    # On the following trading day's snapshot, previous settlement / close
    # corroborate the daily s/c fields without using intraday prices.
    if quote.get('tradedate') and quote['tradedate']>args.as_of:
        validations.append({'snapshotDate':quote['tradedate'],
          'asOfSettlementMatchesNextSnapshotPreviousSettlement':
            main['settle']==number(quote.get('presettlement')),
          'asOfCloseMatchesNextSnapshotPreviousClose':
            main['close']==number(quote.get('preclose')),
          'note':'Only a next actual trading-day snapshot makes these equality checks conclusive.'})
    source={'name':'新浪财经·盘后合约快照' if from_snapshot else '新浪财经·具体合约日线','url':LIST.format(node) if from_snapshot else DAILY+symbol,
            'date':args.as_of,'official':False}
    return {'code':code,'name':name,'sector':sector,'unit':unit,'exchange':'DCE',
      'main':main,'history':history,'contracts':[main],'ranks':[],
      'totalVolume':main['volume'],'totalOi':main['oi'],'totalOiChange':main['oiChange'],
      'aggregateScope':'representative-contract','historyType':'fixed-contract',
      'mainSelection':'已与新浪连续主力当日OHLC/成交量/持仓量匹配' if matched else '新浪盘后合约列表中持仓量较高的代表合约（未确认当日连续主力）',
      'mainMatchedContinuous':matched,'quoteSource':source,
      'historySource':{'name':'新浪财经·具体合约日线＋当日盘后快照' if from_snapshot else '新浪财经·具体合约日线','url':DAILY+symbol,'date':args.as_of,'official':False},
      'rankSource':{'name':'大商所公开会员排名（本次未能读取）','url':'http://www.dce.com.cn/publicweb/quotesdata/memberDealPosiQuotes.html',
                    'date':args.as_of,'status':'unavailable'},
      'rankUnavailableReason':'本次官方接口未提供可读排名，未以零值或模拟席位替代。',
      'sourceNotes':('当日取日期匹配且15:00后的盘后合约快照，已与前一日历史收盘/结算核对；当日日线尚未发布。' if from_snapshot else '')+'仅该具体合约，非品种全合约汇总。s=结算价，p=持仓量；增减仓由相邻实际交易日同合约持仓差分，成交额不可得。',
      'units':{'price':unit,'volume':'手','oi':'手','oiChange':'手','turnover':None},
      'sourceValidation':validations,
      'continuousComparisonSource':{'name':'新浪财经·主力连续（仅校验当日主力身份）','url':DAILY+code.upper()+'0','date':args.as_of},
      'contractDiscoverySource':{'name':'新浪财经·品种合约列表','url':LIST.format(node),'date':quote.get('tradedate')}}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of',default='2026-10-21')
    parser.add_argument('--start',default='2026-07-14')
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--skip-official-probe',action='store_true')
    args=parser.parse_args()
    RAW.mkdir(parents=True,exist_ok=True)
    probe_path=RAW/'official-access.json'
    if not args.skip_official_probe:
        probes=probe_official(args.as_of)
        probe_path.write_text(json.dumps(probes,ensure_ascii=False,indent=2),encoding='utf-8')
    else:
        probes=json.loads(probe_path.read_text(encoding='utf-8')) if probe_path.exists() else []
    markets=[]
    errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch_product,p,args):p for p in PRODUCTS}
        for future in concurrent.futures.as_completed(futures):
            p=futures[future]
            try:
                market=future.result()
                markets.append(market)
                print(p[0],market['main']['contract'],len(market['history']),
                      'main-match' if market['mainMatchedContinuous'] else 'representative',flush=True)
            except Exception as exc:
                errors.append({'code':p[0],'name':p[1],'error':str(exc)})
                print('ERROR',p[0],str(exc),flush=True)
    order={p[0]:i for i,p in enumerate(PRODUCTS)}
    markets.sort(key=lambda m:order[m['code']])
    result={'schema':'domestic-exchange-v1','exchange':'DCE','asOf':args.as_of,
      'fetchedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
      'sources':{'quotes':'新浪财经·具体合约历史日线','official':False},
      'coverage':{'exchange':'DCE','firstDate':args.start,'marketCount':len(markets),
                  'aggregateScope':'representative-contract','rankingAvailable':False,
                  'officialAccessAttempts':probes,'errors':errors},'markets':markets}
    if not markets:
        raise RuntimeError('No validated requested-day DCE data; existing snapshot preserved.')
    output=ROOT/'data'/'dce-markets.json'
    output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('Wrote',output,'markets',len(markets),'errors',len(errors),flush=True)
    if not markets:
        raise SystemExit(1)

if __name__=='__main__':
    main()
