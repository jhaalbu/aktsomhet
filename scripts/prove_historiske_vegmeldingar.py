"""Check archive year counts and download a small historical western-Norway sample."""
import json
from pathlib import Path
from datetime import datetime, timezone
import requests
import pandas as pd

root = Path(__file__).resolve().parents[1]
out = root / 'data/raw/vegmeldingar_research'
out.mkdir(parents=True, exist_ok=True)
url = 'https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer/13/query'
session = requests.Session()
manifest = []


def get(name, params):
    r = session.get(url, params={'f':'json',**params}, timeout=40)
    r.raise_for_status()
    data = r.json()
    (out / (name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest.append(dict(name=name,url=url,params=params,checked_at=datetime.now(timezone.utc).isoformat(),error=data.get('error')))
    if 'error' in data:
        raise RuntimeError(data['error'])
    return data


rows = []
for year in range(2006,2027):
    where = f"FROM_DATE >= timestamp '{year}-01-01 00:00:00' AND FROM_DATE < timestamp '{year+1}-01-01 00:00:00'"
    count = get(f'year_{year}_national',dict(where=where,returnCountOnly='true'))['count']
    rows.append(dict(year=year,national_message_rows=count))
    print(year,count,flush=True)
# Name-based filter is only a sample, not a geographic completeness criterion.
where = "FROM_DATE >= timestamp '2015-01-01 00:00:00' AND FROM_DATE < timestamp '2016-01-01 00:00:00' AND (NAME LIKE '%Hordaland%' OR NAME LIKE '%Sogn og Fjordane%' OR NAME LIKE '%Vestland%')"
data = get('sample_west_2015',dict(where=where,outFields='*',resultRecordCount=50,
           orderByFields='FROM_DATE ASC, EXT_REC_NO ASC',returnGeometry='true'))
sample = pd.DataFrame([f['attributes'] for f in data.get('features',[])])
sample.to_csv(out / 'sample_west_2015.csv',index=False,encoding='utf-8-sig')
pd.DataFrame(rows).to_csv(out / 'archive_year_counts.csv',index=False)
(out / 'historic_probe_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Historical western sample rows:',len(sample),flush=True)
if len(sample):
    print(sample[['NAME','CATEGORY','MSG_DESCRIPTION']].head(8).to_string(index=False),flush=True)
