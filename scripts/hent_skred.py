"""Retrieve NVDB 445, filter by event date and join current road references."""
import argparse
import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
START, END = '2006-10-04', '2026-10-03'
API = 'https://nvdbapiles.atlas.vegvesen.no/vegobjekter/api/v4/vegobjekter/445'


def main(offline=False):
    raw = ROOT / 'data/raw/skred'
    out = ROOT / 'data/processed'
    raw.mkdir(parents=True, exist_ok=True)
    if not offline:
        session = requests.Session()
        session.headers['X-Client'] = 'aktsomhet-ml'
        session.mount('https://', HTTPAdapter(max_retries=Retry(total=5, backoff_factor=1,
                      status_forcelist=[429, 500, 502, 503, 504])))
        # Retrieve ALL dates, then filter event date rather than metadata creation date.
        params = dict(fylke=46, antall=1000, inkluder='alle')
        pages, cursors = [], set()
        while True:
            resp = session.get(API, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            file = raw / f'page_{len(pages)+1:04d}.json'
            file.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            pages.append(dict(file=file.name, count=len(data['objekter']),
                              sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
            print(f"Skred page {len(pages)}: {len(data['objekter'])}", flush=True)
            nxt = data.get('metadata', {}).get('neste', {}).get('start')
            if not nxt or not data['objekter']:
                break
            assert nxt not in cursors
            cursors.add(nxt)
            params['start'] = nxt
        manifest = dict(endpoint=API, filter={'fylke':46}, period=[START, END],
                        retrieved_utc=datetime.now(timezone.utc).isoformat(), pages=pages, complete=True)
        (raw / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    manifest = json.loads((raw / 'manifest.json').read_text(encoding='utf-8'))
    sections = pd.read_csv(out / 'strekningar.csv')
    known = set(sections.strekning_id)
    events, links, unmatched = [], [], []
    excluded, seen = Counter(), set()
    for p in manifest['pages']:
        content = (raw / p['file']).read_bytes()
        assert hashlib.sha256(content).hexdigest() == p['sha256']
        for obj in json.loads(content)['objekter']:
            assert obj['id'] not in seen
            seen.add(obj['id'])
            properties = {e['id']: e.get('verdi') for e in obj.get('egenskaper', [])}
            date = properties.get(2324)
            if not date:
                excluded['missing_event_date'] += 1
                continue
            date = str(date)[:10]
            if not START <= date <= END:
                excluded['outside_period'] += 1
                continue
            geometry = obj.get('geometri') or obj.get('lokasjon', {}).get('geometri', {})
            event = dict(skred_id=obj['id'], dato=date, klokkeslett=properties.get(2325),
                         skredtype=properties.get(2326), losneomrade=properties.get(2328),
                         volum_pa_veg=properties.get(2327), blokkert_veglengde=properties.get(2341),
                         stengning=properties.get(2344), geometri_wkt=geometry.get('wkt'),
                         srid=geometry.get('srid'), versjon=obj['metadata']['versjon'])
            matched, ref_seen = set(), set()
            for ref in obj.get('lokasjon', {}).get('vegsystemreferanser', []):
                road, section = ref.get('vegsystem', {}), ref.get('strekning', {})
                if not section:
                    continue
                sid = f"46_{road.get('vegkategori')}{road.get('fase')}{road.get('nummer')}_S{section.get('strekning')}"
                signature = (sid, section.get('delstrekning'), ref.get('kortform'))
                if signature in ref_seen:
                    continue
                ref_seen.add(signature)
                link = dict(skred_id=obj['id'], dato=date, skredtype=event['skredtype'],
                            strekning_id=sid, delstrekning=section.get('delstrekning'),
                            fra_meter=section.get('fra_meter'), til_meter=section.get('til_meter'),
                            meter=section.get('meter'), kortform=ref.get('kortform'),
                            sideanlegg=bool(ref.get('sideanlegg')), kryss=bool(ref.get('kryssystem')))
                if sid in known:
                    links.append(link)
                    matched.add(sid)
                else:
                    unmatched.append({**link, 'reason':'reference_not_in_road_extract'})
            event['match_antal'] = len(matched)
            events.append(event)
            if not matched and not ref_seen:
                unmatched.append(dict(skred_id=obj['id'], dato=date, reason='no_section_reference'))
    e = pd.DataFrame(events)
    l = pd.DataFrame(links)
    e.to_csv(out / 'skred.csv', index=False, encoding='utf-8-sig')
    l.to_csv(out / 'skred_strekning.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(unmatched).to_csv(out / 'skred_ukopla.csv', index=False, encoding='utf-8-sig')
    # Count distinct events, even when an event has several references on one section.
    daily = l.drop_duplicates(['skred_id','strekning_id']).groupby(['strekning_id','dato']).agg(
        registrerte_skred=('skred_id','nunique')).reset_index()
    daily.to_parquet(out / 'skred_dogn.parquet', index=False)
    counts = l.groupby('strekning_id').skred_id.nunique()
    sections['registrerte_skred_20aar'] = sections.strekning_id.map(counts).fillna(0).astype(int)
    sections.to_csv(out / 'strekningar_med_skred.csv', index=False, encoding='utf-8-sig')
    report = dict(period=[START,END], objects_retrieved=len(seen), events_in_period=len(e),
                  matched_events=int((e.match_antal > 0).sum()), unmatched_events=int((e.match_antal == 0).sum()),
                  sections_with_events=len(counts), excluded=dict(excluded),
                  event_types=e.skredtype.value_counts(dropna=False).to_dict(),
                  joining='Current NVDB references, not a historical road network reconstruction')
    (out / 'skred_kvalitetsrapport.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    main(parser.parse_args().offline)
