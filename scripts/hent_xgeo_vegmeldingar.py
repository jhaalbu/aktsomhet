"""Download the national Xgeo message layer in checked, resumable yearly pages."""
import argparse
import gzip
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/xgeo_vegmeldingar'
URL = 'https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer/13/query'
ORDER = 'FROM_DATE ASC, EXT_REC_NO ASC, VERSION_NO ASC, MSG_NO ASC'
END = '2026-10-03'


def main(offline=False):
    RAW.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=5,backoff_factor=1,
        status_forcelist=[429,500,502,503,504],respect_retry_after_header=True)))
    def request(params):
        for attempt in range(4):
            r = session.get(URL, params={'f':'json',**params}, timeout=90)
            r.raise_for_status()
            data = r.json()
            if 'error' not in data:
                return data
            if attempt == 3:
                raise RuntimeError(data['error'])
            time.sleep(2**attempt)
    manifest = dict(url=URL, fetched_at=datetime.now(timezone.utc).isoformat(), end=END,
                    scope='National layer 13; geographic filtering performed locally', years=[], complete=False)
    total = 0
    for year in range(2006,2027):
        finish = f'{year+1}-01-01' if year < 2026 else '2026-10-04'
        where = f"FROM_DATE >= timestamp '{year}-01-01 00:00:00' AND FROM_DATE < timestamp '{finish} 00:00:00'"
        index = RAW / f'{year}_manifest.json'
        if index.exists():
            saved = json.loads(index.read_text(encoding='utf-8'))
            assert saved['where'] == where
            if saved.get('complete'):
                for page in saved['pages']:
                    assert hashlib.sha256((RAW/page['file']).read_bytes()).hexdigest() == page['sha256']
                manifest['years'].append(saved)
                total += saved['rows']
                print(f'{year}: cached {saved["rows"]}', flush=True)
                continue
        if offline:
            raise RuntimeError(f'Missing completed year {year}')
        before = request(dict(where=where,returnCountOnly='true'))['count']
        pages, signatures = [], set()
        offset = 0
        while offset < before:
            params = dict(where=where,outFields='*',returnGeometry='true',outSR=4326,
                          orderByFields=ORDER,resultOffset=offset,resultRecordCount=1000)
            data = request(params)
            features = data.get('features', [])
            if not features:
                raise RuntimeError(f'Empty page before count reached: {year}/{offset}')
            for feature in features:
                signature = hashlib.sha256(json.dumps(feature,sort_keys=True).encode()).hexdigest()
                if signature in signatures:
                    raise RuntimeError(f'Duplicate row across pages: {year}/{offset}')
                signatures.add(signature)
            file = RAW / f'{year}_{offset:06d}.json.gz'
            payload = gzip.compress(json.dumps(data,ensure_ascii=False).encode('utf-8'),mtime=0)
            temp = file.with_suffix('.tmp')
            temp.write_bytes(payload)
            temp.replace(file)
            pages.append(dict(file=file.name,rows=len(features),sha256=hashlib.sha256(payload).hexdigest(),request=params))
            offset += len(features)
        after = request(dict(where=where,returnCountOnly='true'))['count']
        assert offset == before == after, (year,offset,before,after)
        saved = dict(year=year,where=where,rows=offset,count_before=before,count_after=after,
                     fetched_at=datetime.now(timezone.utc).isoformat(),pages=pages,complete=True)
        index.write_text(json.dumps(saved,indent=2),encoding='utf-8')
        manifest['years'].append(saved)
        total += offset
        print(f'{year}: {offset} rows; {len(pages)} pages',flush=True)
    manifest.update(complete=True, rows=total, completed_at=datetime.now(timezone.utc).isoformat())
    (RAW/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(f'Complete: {total} national message rows',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline',action='store_true')
    main(parser.parse_args().offline)
