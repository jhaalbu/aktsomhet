"""Ask NVE's official GIS service for the current grid-cell inventory."""
import json
import time
from pathlib import Path
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]
URL='https://gis3.nve.no/arcgis/rest/services/geoprocessing/SeNorgeCeller/GPServer/SeNorgeCeller'
cells=pd.read_csv(ROOT/'data/processed/nve_gridceller.csv')
xmin,xmax=int(cells.x.min()-500),int(cells.x.max()+500)
ymin,ymax=int(cells.y.min()-500),int(cells.y.max()+500)
polygon={'rings':[[[xmin,ymin],[xmin,ymax],[xmax,ymax],[xmax,ymin],[xmin,ymin]]],
         'spatialReference':{'wkid':25833}}
folder=ROOT/'data/raw/nve'
session=requests.Session()
response=session.post(URL+'/submitJob',data={'f':'json','in_polygon':json.dumps(polygon)},timeout=120)
response.raise_for_status()
job=response.json()
print(json.dumps(job),flush=True)
assert 'jobId' in job,job
(folder/'mask_job_request.json').write_text(json.dumps({'polygon':polygon,'response':job}),encoding='utf-8')
url=URL+'/jobs/'+job['jobId']
for _ in range(180):
    status=session.get(url,params={'f':'json'},timeout=60).json()
    if status['jobStatus']=='esriJobSucceeded':
        break
    if status['jobStatus'] in ['esriJobFailed','esriJobCancelled']:
        raise ValueError(status)
    time.sleep(2)
else:
    raise TimeoutError(url)
result=session.get(url+'/results/resultat',params={'f':'json'},timeout=120)
result.raise_for_status()
data=result.json()
(folder/'current_grid_mask.json').write_text(json.dumps(data),encoding='utf-8')
value=data['value']
if isinstance(value,str):
    value=json.loads(value)
assert value['SeNorgeCeller']
present=set(value['SeNorgeCeller'])
cells['gis_inventory_present']=cells.cell_index.isin(present)
cells.to_csv(ROOT/'data/processed/nve_gridceller_gis.csv',index=False,encoding='utf-8-sig')
print(cells.gis_inventory_present.value_counts().to_string(),flush=True)
