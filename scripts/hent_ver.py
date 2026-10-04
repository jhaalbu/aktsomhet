"""Download daily NVE GTS for every unique buffer cell, with resumable batches."""
import argparse
import gzip
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT=Path(__file__).resolve().parents[1]
API='https://gts.nve.no/api/MultiPointTimeSeries/ByMapCoordinateCsv'
START, WARMUP, END='2006-10-04','2006-10-02','2026-10-03'
THEMES=['rr','sdfsw','tm','sd','windDirection10m24h06','windSpeed10m24h06','gwb_sssrel']
BATCH=40
LOCAL=threading.local()


def session():
    if not hasattr(LOCAL,'session'):
        LOCAL.session=requests.Session()
        retries=Retry(total=5,backoff_factor=1,status_forcelist=[429,502,503,504],
                      allowed_methods=['GET','POST'],respect_retry_after_header=True)
        LOCAL.session.mount('https://',HTTPAdapter(max_retries=retries))
    return LOCAL.session


def fetch(task):
    theme,batch,metadata=task
    begin=max(WARMUP,metadata['FirstDateInTimeSerie'])
    expected=pd.date_range(begin,END,freq='D')
    body=dict(Theme=theme,StartDate=begin,EndDate=END,Format='json',
              MapCoordinateCsv=', '.join(f'{r.x} {r.y}' for r in batch.itertuples()))
    signature=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()[:20]
    folder=ROOT/'data/weather/cells'/theme
    raw=ROOT/'data/raw/nve/series'/theme
    folder.mkdir(parents=True,exist_ok=True)
    raw.mkdir(parents=True,exist_ok=True)
    target=folder/f'{signature}.parquet'
    info=folder/f'{signature}.json'
    archive=raw/f'{signature}.json.gz'
    if target.exists() and info.exists():
        saved=json.loads(info.read_text(encoding='utf-8'))
        assert saved['request']==body
        return saved
    if archive.exists():
        with gzip.open(archive,'rt',encoding='utf-8') as f:
            data=json.load(f)
    else:
        data=request_batch(body,batch,expected)
        # Save atomically so interrupted downloads can be resumed.
        temp=archive.with_suffix('.tmp')
        with gzip.open(temp,'wb',compresslevel=1) as f:
            f.write(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        temp.replace(archive)
    assert data['TimeResolution']==1440,(theme,data['TimeResolution'])
    actual_start=pd.to_datetime(data['StartDate'],dayfirst=True)
    actual_end=pd.to_datetime(data['EndDate'],dayfirst=True)
    assert actual_start.date()==expected[0].date() and actual_end.date()==expected[-1].date(),(theme,data['StartDate'],data['EndDate'])
    entries=data['CellTimeSeries']
    if isinstance(entries,dict):
        entries=[entries]
    wanted=set(batch.cell_index.astype(int))
    got={int(e['CellIndex']) for e in entries}
    assert len(entries)==len(got) and got==wanted,(theme,wanted-got,got-wanted)
    values={}
    for e in entries:
        assert len(e['Data'])==len(expected),(theme,len(e['Data']),len(expected))
        a=np.array(e['Data'],dtype=np.float32)
        a[a==data['NoDataValue']]=np.nan
        if theme=='windDirection10m24h06':
            assert np.all((np.isnan(a))|((a>=0)&(a<=360)))
        values[str(e['CellIndex'])]=a
    frame=pd.DataFrame(values,index=expected)
    frame.index.name='dato'
    frame=frame.reset_index()
    temporary=target.with_suffix('.tmp')
    frame.to_parquet(temporary,index=False,compression='zstd')
    temporary.replace(target)
    count=int(frame.drop(columns='dato').count().sum())
    result=dict(theme=theme,request=body,endpoint=API,parquet=target.relative_to(ROOT).as_posix(),
                raw=archive.relative_to(ROOT).as_posix(),cells=sorted(wanted),days=len(expected),
                unit=data.get('Unit'),time_resolution=1440,nodata=data['NoDataValue'],
                source_start=data['StartDate'],source_end=data['EndDate'],
                prognosis_start=data.get('PrognoseStartDate'),valid_values=count,
                total_values=len(expected)*len(entries),retrieved_utc=datetime.now(timezone.utc).isoformat(),
                unsupported_cells=[int(e['CellIndex']) for e in entries if e.get('UnsupportedCell')],
                sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    info.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def request_batch(body,batch,expected):
    # Deterministic API errors (missing keys and JSON size) need splitting, not retries.
    response=session().post(API,json=body,timeout=(20,240))
    key_error=response.status_code==500 and 'given key was not present in the dictionary' in response.text
    size_error=response.status_code==500 and 'maxJsonLength' in response.text
    if key_error or size_error:
        if len(batch)==1:
            if not key_error:
                response.raise_for_status()
            row=batch.iloc[0]
            return dict(Theme=body['Theme'],TimeResolution=1440,NoDataValue=65535,
                        StartDate=expected[0].strftime('%d.%m.%Y 00:00'),
                        EndDate=expected[-1].strftime('%d.%m.%Y 00:00'),Unit=None,
                        CellTimeSeries=[dict(CellIndex=int(row.cell_index),X=int(row.x),Y=int(row.y),
                                             Data=[65535]*len(expected),UnsupportedCell=True)])
        half=len(batch)//2
        parts=[]
        for subset in [batch.iloc[:half],batch.iloc[half:]]:
            request={**body,'MapCoordinateCsv':', '.join(f'{r.x} {r.y}' for r in subset.itertuples())}
            parts.append(request_batch(request,subset,expected))
        result={**parts[0],'CellTimeSeries':parts[0]['CellTimeSeries']+parts[1]['CellTimeSeries']}
        units=[p.get('Unit') for p in parts if p.get('Unit') is not None]
        result['Unit']=units[0] if units else None
        return result
    if not response.ok:
        response=session().post(API,json=body,timeout=(20,240))
    response.raise_for_status()
    return response.json()


def main(workers=4,limit=None):
    cells=pd.read_csv(ROOT/'data/processed/nve_gridceller.csv')
    mask=pd.read_csv(ROOT/'data/processed/nve_gridceller_med_maske.csv')
    assert cells.cell_index.tolist()==mask.cell_index.tolist()
    cells['outside_nve_mask']=mask.outside_nve_mask
    excluded_cells=int(cells.outside_nve_mask.sum())
    cells=cells.loc[~cells.outside_nve_mask].drop(columns='outside_nve_mask')
    metadata={t['Name']:t for t in json.loads((ROOT/'data/raw/nve/themes.json').read_text(encoding='utf-8-sig'))}
    tasks=[(theme,cells.iloc[i:i+BATCH],metadata[theme]) for theme in THEMES for i in range(0,len(cells),BATCH)]
    if limit:
        tasks=tasks[:limit]
    report_file=ROOT/'data/weather/download_report.json'
    report_file.parent.mkdir(parents=True,exist_ok=True)
    results,failures=[],[]
    start=time.monotonic()
    def report():
        result=dict(period=[START,END],warmup_start=WARMUP,unique_cells=len(cells),outside_mask_cells=excluded_cells,
                    total_batches=len(tasks),completed_batches=len(results),failed_batches=failures,
                    complete=len(results)==len(tasks) and not limit,limited_test=bool(limit),
                    themes=THEMES,elapsed_seconds=round(time.monotonic()-start,1),batches=results)
        tmp=report_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,indent=2),encoding='utf-8')
        tmp.replace(report_file)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        source=iter(tasks)
        pending={pool.submit(fetch,t):t for t in [next(source,None) for _ in range(workers)] if t is not None}
        while pending:
            done,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                task=pending.pop(future)
                try:
                    results.append(future.result())
                except Exception as exc:
                    failure=dict(theme=task[0],first_cell=int(task[1].cell_index.iloc[0]),error=str(exc))
                    failures.append(failure)
                    print('FAILED '+json.dumps(failure),flush=True)
                if (len(results)+len(failures))%20==0 or len(tasks)<=4:
                    print(f'Weather: {len(results)}/{len(tasks)} batches; failures={len(failures)}; elapsed={time.monotonic()-start:.0f}s',flush=True)
                    report()
                t=next(source,None)
                if t is not None:
                    pending[pool.submit(fetch,t)]=t
    report()
    if failures:
        raise RuntimeError(f'{len(failures)} failed batches; rerun to retry cached download')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    main(args.workers,args.limit)
