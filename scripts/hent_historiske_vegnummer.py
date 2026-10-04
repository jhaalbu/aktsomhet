"""Cache official reform crosswalk PDFs and extract their positioned tables.

Run with bundled Python (pdfplumber). No network needed when PDFs are cached.
"""
import hashlib
import json
from pathlib import Path
import urllib.request
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/raw/historiske_vegnummer'
OUT.mkdir(parents=True, exist_ok=True)
sources = []
for county, name in [(12,'Hordaland'), (14,'Sogn%20og%20Fjordane')]:
    url = f'https://labs.vegdata.no/nvdbstatus/regionreform/vegnummer/nyevegnummerlister/20210615%20Nye%20vegnummer%20-%20F{county}%20{name}.pdf'
    path = OUT/f'F{county}.pdf'
    if not path.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())
    with pdfplumber.open(path) as pdf:
        tables = [page.extract_tables() for page in pdf.pages]
        texts = [page.extract_text(layout=False) for page in pdf.pages]
    (OUT/f'F{county}_tables.json').write_text(json.dumps(tables, ensure_ascii=False, indent=2),encoding='utf-8')
    (OUT/f'F{county}_text.txt').write_text('\n'.join(texts),encoding='utf-8')
    sources.append(dict(county=county,url=url,file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(OUT/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(sources,indent=2))
