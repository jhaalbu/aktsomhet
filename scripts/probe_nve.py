import json
from pathlib import Path
import requests

out=Path('data/raw/nve')
session=requests.Session()
for coords in ['30001 6670001','30499 6670499','30501 6670501','29999 6669999','30250 6670250', '31000 6670000']:
    body=dict(Theme='rr',StartDate='2006-10-02',EndDate='2006-10-05',Format='json',MapCoordinateCsv=coords)
    r=session.post('https://gts.nve.no/api/MultiPointTimeSeries/ByMapCoordinateCsv',json=body,timeout=60)
    print(coords,r.status_code,r.text[:500],flush=True)
    if r.ok:
        (out / ('probe_'+coords.replace(' ','_')+'.json')).write_text(r.text,encoding='utf-8')
body=dict(Theme='rr',StartDate='2006-10-02',EndDate='2006-10-05',Format='json',Method='avg',CellIndexCsv='1589454,1589456,1587064')
r=session.post('https://gts.nve.no/api/AggregationTimeSeries/ByCellIndexCsv',json=body,timeout=60)
print('aggregation',r.status_code,r.text[:1000])
(out / 'probe_aggregation.json').write_text(r.text,encoding='utf-8')
