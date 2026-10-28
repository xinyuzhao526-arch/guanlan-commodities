"""Download public GFEX futures daily reports and member position rankings.

Run: python scripts/source_gfex.py --start 2026-07-14 --as-of 2026-10-21
Uses the same public POST endpoints documented by AKShare's GFEX adapters.
HTTP is deliberate: the official HTTPS hostname currently fails certificate
verification. No TLS verification is disabled. Raw JSON is cached on disk.
"""
import argparse
import datetime as dt
import json
import pathlib
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data' / 'raw' / 'gfex'
BASE = 'http://www.gfex.com.cn'
QUOTES = BASE + '/u/interfacesWebTiDayQuotes/loadList'
RANKS = BASE + '/u/interfacesWebTiMemberDealPosiQuotes/loadList'
QUOTE_PAGE = BASE + '/gfex/rihq/hqsj_tjsj.shtml'
RANK_PAGE = BASE + '/gfex/rcjccpm/hqsj_tjsj.shtml'
META = {
    'si': ('工业硅', '有色金属', '元/吨'),
    'lc': ('碳酸锂', '有色金属', '元/吨'),
    'ps': ('多晶硅', '有色金属', '元/吨'),
    'pt': ('铂', '贵金属', '元/克'),
    'pd': ('钯', '贵金属', '元/克'),
}


def number(value):
    try:
        result = float(str(value).replace(',', ''))
        return result if result == result else None
    except (TypeError, ValueError):
        return None


def post(url, payload, cache_name):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (cache_name + '.json')
    for attempt in range(2):
        try:
            if path.exists():
                doc = json.loads(path.read_text(encoding='utf-8'))
            else:
                request = urllib.request.Request(url,
                    data=urllib.parse.urlencode(payload).encode(),
                    headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.gfex.com.cn/'})
                with urllib.request.urlopen(request, timeout=25) as response:
                    raw = response.read()
                doc = json.loads(raw)
                time.sleep(.4)
            if str(doc.get('code')) != '0' or not isinstance(doc.get('data'), list):
                path.with_suffix('.error.json').write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
                raise ValueError(f"Official API returned code={doc.get('code')}, msg={doc.get('msg')}, no successful records")
            for key, expected in payload.items():
                actual = doc.get('param', {}).get(key)
                if actual is not None and actual not in ([str(expected)], str(expected)):
                    raise ValueError('Official API parameter mismatch: ' + key)
            if not path.exists():
                path.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
            return doc
        except Exception:
            if attempt:
                raise
            time.sleep(.6)


def parse_quotes(doc, day):
    rows = []
    for raw in doc['data']:
        code = str(raw.get('varietyOrder', '')).lower()
        month = str(raw.get('delivMonth', '')).strip()
        if code not in META or len(month) != 4 or not month.isdigit():
            continue
        row = {'code': code, 'contract': code + month, 'date': day}
        fields = {'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                  'settle': 'clearPrice', 'prevSettle': 'lastClear',
                  'volume': 'volumn', 'oi': 'openInterest', 'oiChange': 'diffI',
                  'turnover': 'turnover'}
        for key, field in fields.items():
            row[key] = number(raw.get(field))
        for key in ('open', 'high', 'low', 'close', 'settle', 'prevSettle'):
            if row[key] is not None and row[key] <= 0:
                row[key] = None
        row['changePct'] = ((row['close'] / row['prevSettle'] - 1) * 100
                            if row['close'] and row['prevSettle'] else None)
        rows.append(row)
    return rows


def rankings(code, contract, date):
    """data_type 2 is long, 3 is short; preserve each independent member list."""
    by_rank = {}
    for typ, prefix in ((2, 'long'), (3, 'short')):
        payload = {'trade_date': date.replace('-', ''), 'trade_type': '0',
                   'variety': code, 'contract_id': contract, 'data_type': str(typ)}
        doc = post(RANKS, payload, f'rank-{date}-{contract}-{typ}')
        for raw in doc['data']:
            try:
                rank = int(raw.get('contractId'))
            except (TypeError, ValueError):
                continue
            if not 1 <= rank <= 20:
                continue
            row = by_rank.setdefault(rank, {'rank': rank,
                'longName': None, 'long': None, 'longChange': None,
                'shortName': None, 'short': None, 'shortChange': None})
            row[prefix + 'Name'] = raw.get('abbr') or None
            row[prefix] = number(raw.get('todayQty'))
            row[prefix + 'Change'] = number(raw.get('qtySub', raw.get('todayQtyChg')))
    return [by_rank[r] for r in sorted(by_rank)]


def nullable_sum(rows, key):
    values = [r.get(key) for r in rows]
    return sum(values) if values and all(v is not None for v in values) else None


def build(start, asof):
    parsed, unavailable = {}, []
    day = asof
    while day >= start:
        if day.weekday() < 5:
            try:
                doc = post(QUOTES, {'trade_date': day.strftime('%Y%m%d'), 'trade_type': '0'},
                           'quotes-' + day.isoformat())
                rows = parse_quotes(doc, day.isoformat())
                if rows:
                    parsed[day.isoformat()] = rows
                else:
                    unavailable.append({'date': day.isoformat(), 'reason': 'Official API returned no futures records; may be a nontrading day'})
            except Exception as exc:
                unavailable.append({'date': day.isoformat(), 'reason': str(exc)})
        day -= dt.timedelta(days=1)
    if not parsed:
        raise RuntimeError('No validated official GFEX quotes; existing snapshot preserved')
    latest = max(parsed)
    if latest != asof.isoformat():
        raise RuntimeError(f'GFEX latest report {latest} differs from requested {asof}; existing snapshot preserved')
    markets, rank_errors = [], []
    for code, (name, sector, unit) in META.items():
        contracts = sorted((r for r in parsed[latest] if r['code'] == code),
                           key=lambda r: r['oi'] if r['oi'] is not None else -1, reverse=True)
        valid = [r for r in contracts if r['close'] is not None and (r['volume'] or 0) > 0]
        if not valid:
            continue
        main = valid[0]
        history = [r for day in sorted(parsed) for r in parsed[day]
                   if r['contract'] == main['contract'] and r['close'] is not None]
        try:
            ranks = rankings(code, main['contract'], latest)
        except Exception as exc:
            ranks = []
            rank_errors.append({'code': code, 'reason': str(exc)})
        markets.append({'code': code, 'name': name, 'sector': sector, 'unit': unit,
            'exchange': 'GFEX', 'main': main, 'history': history,
            'contracts': contracts, 'ranks': ranks,
            'totalVolume': nullable_sum(contracts, 'volume'),
            'totalOi': nullable_sum(contracts, 'oi'),
            'totalOiChange': nullable_sum(contracts, 'oiChange'),
            'quoteSource': {'name': '广期所官方日行情', 'url': QUOTE_PAGE, 'api': QUOTES, 'official': True,
                            'date': latest, 'params': {'trade_date': latest.replace('-', ''), 'trade_type': '0'}},
            'rankSource': {'name': '广期所官方会员持仓排名', 'url': RANK_PAGE, 'api': RANKS, 'official': True,
                           'date': latest, 'contract': main['contract'], 'dataTypes': {'long': '2', 'short': '3'}},
            'historySource': {'name': '广期所官方日行情', 'url': QUOTE_PAGE, 'api': QUOTES, 'official': True},
            'historyType': 'fixed-contract', 'historyStatus': 'complete-window',
            'aggregateScope': 'all-contracts',
            'rankingStatus': 'available' if ranks else 'unavailable',
            'volumeUnit': '手（单边）', 'oiUnit': '手（单边）', 'turnoverUnit': '万元'})
    return {'schema': 'domestic-v1', 'asOf': latest,
        'fetchedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
        'sources': {'quotes': QUOTES, 'ranks': RANKS, 'landing': QUOTE_PAGE},
        'sourceStatus': {'note': '广期所官方公开日行情，全合约汇总；铂、钯会员排名接口未返回成功记录，排名留空。',
                         'url': QUOTE_PAGE, 'quoteUrl': QUOTES, 'rankUrl': RANKS, 'official': True},
        'coverage': {'exchanges': ['GFEX'], 'firstDate': min(parsed),
                     'tradingDays': len(parsed), 'unavailableDates': unavailable,
                     'rankingErrors': rank_errors,
                     'note': '官网公开HTTP接口；HTTPS证书主机校验失败。会员排名按多头、空头独立请求，非全市场净持仓。'},
        'markets': markets}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2026-07-14')
    parser.add_argument('--as-of', default='2026-10-21')
    args = parser.parse_args()
    data = build(dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.as_of))
    target = ROOT / 'data' / 'gfex-markets.json'
    target.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    print(json.dumps({'asOf': data['asOf'], 'markets': len(data['markets']),
                      'tradingDays': data['coverage']['tradingDays'],
                      'rankingMarkets': sum(bool(m['ranks']) for m in data['markets']),
                      'unavailableDates': len(data['coverage']['unavailableDates'])}, ensure_ascii=False))
