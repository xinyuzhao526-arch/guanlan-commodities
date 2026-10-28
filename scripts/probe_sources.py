"""Check current-day official reports before spending time on the history window."""
import argparse
import datetime as dt
from source_czce import fetch, parse_quotes as czce_quotes
from source_gfex import post, parse_quotes as gfex_quotes, QUOTES

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--as-of', required=True)
args = parser.parse_args()
day = dt.date.fromisoformat(args.as_of)
doc = fetch(day)
if 'error' in doc or not czce_quotes(doc):
    raise RuntimeError('CZCE requested-day report unavailable: ' + str(doc.get('error')))
doc = post(QUOTES, {'trade_date': day.strftime('%Y%m%d'), 'trade_type': '0'}, 'quotes-' + args.as_of)
if not gfex_quotes(doc, args.as_of):
    raise RuntimeError('GFEX requested-day report has no futures records.')
print('Current-day CZCE and GFEX official reports verified.', flush=True)
