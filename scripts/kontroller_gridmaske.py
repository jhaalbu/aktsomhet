"""Validate cells outside NVE's published mask against the live GTS API."""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd
from hent_ver import session

ROOT=Path(__file__).resolve().parents[1]
cells=pd.read_csv(ROOT/'data/processed/nve_gridceller.csv')
mask=np.load(ROOT/'data/raw/nve/norway_mask.npy')
outside=mask.ravel()[cells.cell_index.to_numpy()]
raw=ROOT/'data/raw/nve/mask_checks'
raw.mkdir(parents=True,exist_ok=True)


def check(row):
    file=raw/f'{row.cell_index}.json'
    if file.exists():
        return json.loads(file.read_text(encoding='utf-8'))
    url=f'https://gts.nve.no/api/GridTimeSeries/{row.x}/{row.y}/2025-01-01/2025-01-01/rr.json'
    # 500 means absent cell only when the server explicitly says so.
    response=session().get(url,timeout=60)
    if response.ok:
        data=response.json()
        assert data['TimeResolution']==1440
        result=dict(cell_index=int(row.cell_index),supported=True,url=url)
    elif response.status_code in [400,500] and 'No cell exists for coordinates' in response.text:
        result=dict(cell_index=int(row.cell_index),supported=False,url=url,error=response.json()['Error'])
    else:
        response.raise_for_status()
        raise ValueError(response.text[:200])
    file.write_text(json.dumps(result),encoding='utf-8')
    return result


if __name__=='__main__':
    results=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(check,r) for r in cells.loc[outside].itertuples()]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results)%100==0:
                print(f'Mask verified {len(results)}/{sum(outside)}',flush=True)
    verified={r['cell_index']:r['supported'] for r in results}
    cells['outside_nve_mask']=[not verified.get(int(i),True) for i in cells.cell_index]
    cells.to_csv(ROOT/'data/processed/nve_gridceller_med_maske.csv',index=False,encoding='utf-8-sig')
    print(cells.outside_nve_mask.value_counts().to_string())
