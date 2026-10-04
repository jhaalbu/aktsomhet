"""Read-only probes of public message catalogues; no archive assumed."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

root = Path(__file__).resolve().parents[1]
out = root / 'data/raw/vegmeldingar_research'
out.mkdir(parents=True, exist_ok=True)
session = requests.Session()
results = []


def probe(name, url, params):
    item = dict(name=name, url=url, parameters=params, checked_at=datetime.now(timezone.utc).isoformat())
    try:
        r = session.get(url, params=params, timeout=25)
        item['status'] = r.status_code
        try:
            data = r.json()
        except ValueError:
            data = dict(text_preview=r.text[:1000])
        (out / (name+'.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        item['response_file'] = name+'.json'
    except requests.RequestException as e:
        data = {}
        item['error'] = type(e).__name__
    results.append(item)
    print(name, item.get('status', item.get('error')), flush=True)
    return data


for label, base in [
    ('nve_gis3', 'https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer'),
    ('nve_kart', 'https://kart.nve.no/enterprise/rest/services/Mapservices/XgeoVeimelding2/MapServer')]:
    metadata = probe(label, base, {'f':'json'})
    print('Layers:', metadata.get('layers'), flush=True)
    for layer in metadata.get('layers', []):
        if any(word in layer['name'].lower() for word in ['skred', 'ras', 'flom']):
            url = base+'/'+str(layer['id'])
            detail = probe(label+'_'+str(layer['id']), url, {'f':'json'})
            fields = {f['name'] for f in detail.get('fields', [])}
            if 'FROM_DATE' in fields:
                stats = [dict(statisticType=t, onStatisticField='FROM_DATE', outStatisticFieldName=n)
                         for t,n in [('min','earliest'),('max','latest'),('count','records')]]
                stats_data = probe(label+'_'+str(layer['id'])+'_dates', url+'/query',
                    {'f':'json', 'where':'1=1', 'outStatistics':json.dumps(stats), 'returnGeometry':'false'})
                print(stats_data.get('features', stats_data.get('error')), flush=True)
probe('svv_ogc_collection', 'https://ogckart-sn1.atlas.vegvesen.no/ogc/features/v1/collections/datex_3_1:SituationSimple', {'f':'json'})
for layer_id in [5,13]:
    base = f'https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer/{layer_id}/query'
    for suffix, extra in [('count', {'returnCountOnly':'true'}),
                          ('earliest', {'outFields':'*','resultRecordCount':1,'returnGeometry':'true','orderByFields':'FROM_DATE ASC'}),
                          ('latest', {'outFields':'*','resultRecordCount':1,'returnGeometry':'true','orderByFields':'FROM_DATE DESC'})]:
        data = probe(f'nve_simple_{layer_id}_{suffix}', base, {'f':'json','where':'1=1',**extra})
        print(str(data)[:700], flush=True)
items = probe('svv_ogc_sample', 'https://ogckart-sn1.atlas.vegvesen.no/ogc/features/v1/collections/datex_3_1:SituationSimple/items',
              {'f':'application/geo+json','limit':1})
print('OGC fields:',list(items.get('features',[{}])[0].get('properties',{})) if items.get('features') else items.get('error'),flush=True)
(out / 'probe_manifest.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
