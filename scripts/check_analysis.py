"""Independent arithmetic fixtures and data-boundary checks for derived evidence."""
import copy, datetime as dt, math
from analyze_markets import derive, percentile, analyze

days=[(dt.date(2026,1,1)+dt.timedelta(days=i)).isoformat() for i in range(30)]
hist=[{'date':d,'contract':'test2606','close':100+i,'high':100+i+.2,'low':100+i-.2,'volume':500 if i==29 else 100,'oi':1000+10*i} for i,d in enumerate(days)]
m={'code':'test','name':'test','sector':'test','exchange':'TEST','main':hist[-1], 'history':hist,'totalOiChange':999999,'ranks':[
 {'longName':'A','shortName':'C','long':60,'short':10,'longChange':3,'shortChange':2},
 {'longName':'B','shortName':'D','long':40,'short':20,'longChange':2,'shortChange':1}]}
a=derive(m,days)
def near(actual,expected): assert actual is not None and math.isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-10),(actual,expected)
near(a['return5'],(129/124-1)*100);near(a['return20'],(129/109-1)*100)
near(a['ma5'],127);near(a['ma20'],119.5);near(a['ma20Slope5'],(119.5/114.5-1)*100)
near(a['volumeRatio20'],5);near(a['atr14'],1.2)
near(a['fixedOiChange'],10);near(a['seatDifference'],70);near(a['seatDifferencePctOi'],70/1290*100)
near(a['seatDeltaDifference'],2);assert a['status']=='多维同向';assert a['quadrant']=='涨价增仓';assert a['breakoutDirection']==1
near(percentile(1,[1,1,2]),100/3);near(percentile(2,[1,1,2]),250/3)

missing=copy.deepcopy(m);missing['history']=[h for h in missing['history'] if h['date']!=days[-2]]
b=derive(missing,days)
assert b['return1'] is None and b['fixedOiChange'] is None and b['ma20'] is None and b['volatility20'] is None and b['atr14'] is None
assert b['missingRecent20']==1 and b['status']!='多维同向'

future=copy.deepcopy(m);future['history'].append({'date':'2027-01-01','contract':'test2606','close':999999,'high':999999,'low':999999,'volume':999999,'oi':999999})
assert derive(future,days+['2027-01-01'])==a,'Future observation leaked into snapshot'
aggregate=copy.deepcopy(m);aggregate['totalOiChange']=-999999
assert derive(aggregate,days)==a,'Product aggregate contaminated fixed-contract evidence'

no_seats=copy.deepcopy(m);no_seats['ranks']=[]
c=derive(no_seats,days);assert c['seatDifference'] is None and c['dimensionsAvailable']==2 and c['status']!='多维同向'
opposed=copy.deepcopy(m);opposed['ranks'][0]['longChange']=-30
c=derive(opposed,days);assert c['seatMarginalConflict'] and c['status']=='存在分歧'
constant=copy.deepcopy(m)
for h in constant['history']:h.update(close=100,high=101,low=99,volume=100)
constant['main']=constant['history'][-1]
c=derive(constant,days);near(c['return20'],0);near(c['volatility20'],0);near(c['atr14'],2);near(c['volumeRatio20'],1)
assert c['trendDirection']==0
print('PASS: independently known returns, MA slope, volume baseline, true range, seat arithmetic, ties, missing days, no lookahead, fixed-contract isolation, missing seats, contradictory seat changes.')
