"""Save the public GTS catalogue and NVE's published seNorge mask."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'data/raw/nve'
folder.mkdir(parents=True,exist_ok=True)
sources={
    'themes.json':'https://gts.nve.no/api/GridTimeSeries/Themes/json',
    'norway_mask.npy':'https://raw.githubusercontent.com/NVE/pysenorge/master/pysenorge/resources/norway_mask.npy'}
manifest=[]
for name,url in sources.items():
    response=requests.get(url,timeout=120)
    response.raise_for_status()
    file=folder/name
    file.write_bytes(response.content)
    manifest.append(dict(file=name,url=url,sha256=hashlib.sha256(response.content).hexdigest(),
                         retrieved_utc=datetime.now(timezone.utc).isoformat()))
(folder/'metadata_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Saved NVE theme catalogue and published mask')
