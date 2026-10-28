"""Export the dashboard as one offline HTML file, without a server or CDN."""
import json
import pathlib
import re
import argparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
html = (ROOT / 'dist/index.html').read_text(encoding='utf-8')
css = (ROOT / 'dist/style.css').read_text(encoding='utf-8')
css = re.sub(r'@import\s+url\([^)]*\)\s*;', '', css)
assert css.lstrip().startswith(':root{'), 'Unexpected stylesheet header after removing external fonts.'
js = (ROOT / 'dist/app.js').read_text(encoding='utf-8')
old = "try{const response=await fetch('./data.json',{cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);DATA=await response.json();"
assert old in js, 'Application data loader changed; inspect before bundling.'
js = js.replace(old, "try{DATA=JSON.parse(document.getElementById('embedded-data').textContent);")
js = js.replace('当前为手动生成并发布的数据快照，尚未配置无人值守更新。', '当前为内嵌数据快照，更新数据后重新生成 HTML 即可；不会自动联网刷新。')
data = json.loads((ROOT / 'dist/data.json').read_text(encoding='utf-8'))
assert data['schema'] == 'domestic-v1'
payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('&', '\\u0026')
html = html.replace('<link rel="stylesheet" href="style.css">', '<style>' + css + '</style>')
html = re.sub(r'<a[^>]*class="offline-download"[^>]*>.*?</a>', '', html)
html = html.replace('<script type="module" src="app.js"></script>', '<script id="embedded-data" type="application/json">' + payload + '</script><script>' + js.replace('</script', '<\\/script') + '</script>')
assert 'fetch(' not in html and '@import' not in html
assert 'src="app.js"' not in html and 'href="style.css"' not in html
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=pathlib.Path, default=ROOT.parent / '商品研究终端.html')
out = parser.parse_args().output.resolve()
out.write_text(html, encoding='utf-8')
print(json.dumps({'file': str(out), 'bytes': out.stat().st_size, 'asOf': data['asOf'], 'markets': len(data['markets'])}, ensure_ascii=False))
