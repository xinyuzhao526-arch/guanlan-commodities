from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'dist/app.js';s=p.read_text(encoding='utf-8')
ui=(ROOT/'scripts/terminal_ui.js').read_text(encoding='utf-8')
if '// BEGIN TERMINAL UI' in s:
 a=s.index('// BEGIN TERMINAL UI');b=s.index('// END TERMINAL UI',a)+len('// END TERMINAL UI');s=s[:a]+ui+s[b:]
else:s=s.replace('function render(){',ui+'\nfunction render(){')
# Previous repeated upgrades had duplicated this label; retain one.
label='''<span class="chart-unit">${m.aggregateScope==='representative-contract'?(m.mainMatchedContinuous?'已匹配主力合约':'盘后代表合约'):'持仓量最大合约'}</span>'''
while label+label in s:s=s.replace(label+label,label)
p.write_text(s,encoding='utf-8')
css='\n'.join((ROOT/'scripts'/name).read_text(encoding='utf-8') for name in ['terminal.css','terminal_readability.css'])
(ROOT/'dist/style.css').write_text(css,encoding='utf-8')
print('Terminal interface installed.')
