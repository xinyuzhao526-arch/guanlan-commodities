"""Download and normalize CZCE official daily quotes and member rankings.

Raw pipe-separated reports are cached unchanged.  Current reports are UTF-8;
GB18030 is supported for older official files.  Never fabricate missing fields.
Run: python scripts/source_czce.py --as-of 2026-10-21 --start 2026-07-14
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import pathlib
import re
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data' / 'raw' / 'czce'
META = {
    'AP': ('苹果', '农产品'), 'CF': ('棉花', '农产品'),
    'CJ': ('红枣', '农产品'), 'CY': ('棉纱', '农产品'),
    'FG': ('玻璃', '能源化工'), 'JR': ('粳稻', '农产品'),
    'LR': ('晚籼稻', '农产品'), 'MA': ('甲醇', '能源化工'),
    'OI': ('菜油', '农产品'), 'PF': ('短纤', '能源化工'),
    'PK': ('花生', '农产品'), 'PL': ('丙烯', '能源化工'),
    'PM': ('普麦', '农产品'), 'PR': ('瓶片', '能源化工'),
    'PX': ('对二甲苯', '能源化工'), 'RI': ('早籼稻', '农产品'),
    'RM': ('菜粕', '农产品'), 'RS': ('菜籽', '农产品'),
    'SA': ('纯碱', '能源化工'), 'SF': ('硅铁', '黑色金属'),
    'SH': ('烧碱', '能源化工'), 'SM': ('锰硅', '黑色金属'),
    'SR': ('白糖', '农产品'), 'TA': ('PTA', '能源化工'),
    'UR': ('尿素', '能源化工'), 'WH': ('强麦', '农产品'),
    'ZC': ('动力煤', '能源化工'),
}


def number(value):
    try:
        return float(str(value).strip().replace(',', ''))
    except (ValueError, TypeError):
        return None


def report_url(day, kind='daily'):
    filename = 'FutureDataDaily.txt' if kind == 'daily' else 'FutureDataHolding.txt'
    return f'https://www.czce.com.cn/cn/DFSStaticFiles/Future/{day:%Y}/{day:%Y%m%d}/{filename}'


def decode(raw):
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    raise ValueError('No recognized report encoding')


def fetch(day, kind='daily'):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f'{day:%Y%m%d}-{kind}.txt'
    url = report_url(day, kind)
    error = None
    for attempt in range(2):
        try:
            if path.exists():
                raw = path.read_bytes()
            else:
                request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.czce.com.cn/'})
                with urllib.request.urlopen(request, timeout=16) as response:
                    raw = response.read()
            text, encoding = decode(raw)
            if '<html' in text[:1000].lower() or '|' not in text:
                raise ValueError('Not a pipe-separated official report')
            if day.isoformat() not in text and day.strftime('%Y%m%d') not in text and day.strftime('%Y/%m/%d') not in text:
                raise ValueError('Report date does not match requested date')
            if not path.exists():
                path.write_bytes(raw)
            return {'date': day.isoformat(), 'url': url, 'text': text, 'encoding': encoding}
        except Exception as exc:
            error = str(exc)
            if '404' in error:
                break
            if attempt == 0:
                time.sleep(.25)
    return {'date': day.isoformat(), 'url': url, 'error': error}


def parse_quotes(doc):
    """Header: 合约代码|昨结算|今开盘|最高价|最低价|今收盘|今结算|
    涨跌1|涨跌2|成交量(手)|持仓量|增减量|成交额(万元)|交割结算价.
    涨跌1 may use settlement for an inactive contract: derive close return only
    where an actual positive close exists. Keep inactive contracts in aggregates.
    """
    rows = []
    header = None
    fields = {'prevSettle': '昨结算', 'open': '今开盘', 'high': '最高价',
              'low': '最低价', 'close': '今收盘', 'settle': '今结算',
              'volume': '成交量(手)', 'oi': '持仓量', 'oiChange': '增减量',
              'turnover': '成交额(万元)'}
    for line in doc['text'].splitlines():
        cells = [c.strip() for c in line.split('|')]
        if cells[0] == '合约代码':
            header = cells
            continue
        match = re.fullmatch(r'([A-Z]+)(\d{3,4})', cells[0])
        if not match or not header:
            continue
        code, month = match.groups()
        values = dict(zip(header, cells))
        row = {'code': code.lower(), 'contract': cells[0], 'date': doc['date']}
        for key, field in fields.items():
            row[key] = number(values.get(field))
        for field in ('open', 'high', 'low', 'close'):
            if row[field] is not None and row[field] <= 0:
                row[field] = None
        row['changePct'] = ((row['close'] / row['prevSettle'] - 1) * 100
                            if row['close'] and row['prevSettle'] else None)
        rows.append(row)
    if not rows:
        raise ValueError('No contracts found with verified quote header')
    return rows


def parse_ranks(doc):
    """Official sections start with 合约：AP701 日期：2026-10-21.
    Columns: 名次|会员简称|成交量|增减|会员简称|持买单量|增减|
    会员简称|持卖单量|增减. Product summary sections are not contract ranks.
    """
    result = {}
    contract = None
    for line in doc['text'].splitlines():
        match = re.search(r'合约[：:]\s*([A-Z]+\d{3,4})\b', line)
        if match:
            contract = match.group(1)
            result.setdefault(contract, [])
            continue
        if re.search(r'品种[：:]', line):
            contract = None
            continue
        cells = [c.strip() for c in line.split('|')]
        if contract and len(cells) >= 10 and cells[0].isdigit() and 1 <= int(cells[0]) <= 20:
            result[contract].append({'rank': int(cells[0]),
                'longName': cells[4], 'long': number(cells[5]), 'longChange': number(cells[6]),
                'shortName': cells[7], 'short': number(cells[8]), 'shortChange': number(cells[9])})
    return result


def build(asof, start, workers=4):
    days = [start + dt.timedelta(days=i) for i in range((asof-start).days+1)
            if (start + dt.timedelta(days=i)).weekday() < 5]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        docs = list(pool.map(fetch, days))
    good = []
    parsed = {}
    for doc in docs:
        if 'text' in doc:
            try:
                parsed[doc['date']] = parse_quotes(doc)
                good.append(doc)
            except ValueError as exc:
                doc['error'] = str(exc)
    good.sort(key=lambda d: d['date'])
    if not good:
        raise RuntimeError('CZCE official quotes unavailable; no snapshot overwritten')
    latest = good[-1]
    if latest['date'] != asof.isoformat():
        raise RuntimeError(f'CZCE latest available date {latest["date"]} differs from requested {asof}; no snapshot overwritten')
    rank_doc = fetch(asof, 'holding')
    ranks = parse_ranks(rank_doc) if 'text' in rank_doc else {}
    markets = []
    for code in sorted({r['code'].upper() for r in parsed[latest['date']]}):
        contracts = sorted((r for r in parsed[latest['date']] if r['code'] == code.lower()),
                           key=lambda r: r['oi'] or 0, reverse=True)
        active = [r for r in contracts if r['close'] and (r['volume'] or 0) > 0]
        # Zero-volume products must not present stale settlement as an actual close.
        if not active:
            continue
        if code not in META:
            raise ValueError(f'Unmapped CZCE product: {code}')
        main = active[0]
        history = [r for day in sorted(parsed) for r in parsed[day]
                   if r['contract'] == main['contract'] and r['close']]
        markets.append({'code': code.lower(), 'name': META[code][0], 'sector': META[code][1],
            'unit': '元/吨（折百）' if code == 'SH' else '元/吨', 'exchange': 'CZCE', 'main': main, 'history': history,
            'contracts': contracts, 'ranks': ranks.get(main['contract'], []),
            'totalVolume': sum(r['volume'] for r in contracts) if all(r['volume'] is not None for r in contracts) else None,
            'totalOi': sum(r['oi'] for r in contracts) if all(r['oi'] is not None for r in contracts) else None,
            'totalOiChange': sum(r['oiChange'] for r in contracts) if all(r['oiChange'] is not None for r in contracts) else None,
            'quoteSource': {'name': '郑州商品交易所每日行情', 'url': latest['url'], 'date': latest['date']},
            'rankSource': {'name': '郑州商品交易所每日持仓排名', 'url': rank_doc['url'], 'date': latest['date']},
            'historySource': {'name': '郑州商品交易所逐日行情', 'url': latest['url']},
            'historyType': 'fixed-contract', 'aggregateScope': 'all-contracts',
            'rankingStatus': 'available' if ranks.get(main['contract']) else 'unavailable',
            'turnoverUnit': '万元', 'oiChangeStatus': 'official-reported',
            'historyStatus': 'full-window' if len(history) == len(good) else 'sparse-traded-close',
            'historyNote': None if len(history) == len(good) else '仅保留官方正收盘价；未成交且收盘价为零的交易日不填充、不插值'})
    output = {'schema': 'domestic-v1', 'asOf': latest['date'],
        'fetchedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'markets': markets,
        'sources': {'quotes': latest['url'], 'ranks': rank_doc['url'], 'landing': 'https://www.czce.com.cn/'},
        'coverage': {'exchanges': ['CZCE'], 'firstDate': good[0]['date'], 'tradingDays': len(good),
            'quoteProductCount': len({r['code'] for r in parsed[latest['date']]}),
            'inactiveProducts': [code.lower() for code in sorted({r['code'].upper() for r in parsed[latest['date']]}) if code.lower() not in {m['code'] for m in markets}],
            'unavailableDates': [{'date': d['date'], 'reason': d['error']} for d in docs if 'error' in d],
            'rankingError': rank_doc.get('error'),
            'rankingContracts': len(ranks), 'rankingMarkets': sum(bool(m['ranks']) for m in markets)},
        'sourceStatus': {'quotes': 'official-available', 'rankings': 'official-available' if ranks else 'unavailable',
            'encoding': latest['encoding'], 'historyReports': [{'date': d['date'], 'url': d['url']} for d in good]},
        'methodology': {'main': 'Maximum open interest among contracts with positive reported close and volume on snapshot date',
            'history': 'Snapshot representative contract tracked backwards; no rolling or adjustment',
            'changePct': '(reported close / previous settlement - 1) * 100',
            'aggregate': 'All futures contracts, excluding product subtotals and grand total',
            'inactive': 'Products without a traded close on snapshot date omitted; zero OHLC treated as unavailable'}}
    assert markets and all(m['main']['date'] == latest['date'] and m['history'][-1]['date'] == latest['date'] for m in markets)
    dest = ROOT / 'data' / 'czce-markets.json'
    dest.write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', default='2026-10-21')
    parser.add_argument('--start', default='2026-07-14')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    result = build(dt.date.fromisoformat(args.as_of), dt.date.fromisoformat(args.start), args.workers)
    print(json.dumps({'asOf': result['asOf'], 'markets': len(result['markets']), 'coverage': result['coverage']}, ensure_ascii=True))
