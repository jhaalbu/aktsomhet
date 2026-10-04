"""Number-filter ablation only: preserve production labels and flag possible renumbering."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/processed/vegmeldingar/vegnummer_diagnose'
OUT.mkdir(exist_ok=True)
df=pd.read_parquet(ROOT/'data/processed/vegmeldingar/meldingar_vestland_kandidatar.parquet')
df=df.loc[df.klasse.eq('meldt_skred') & df.dato.between('2013-01-01','2026-10-03')].copy()
roads=pd.read_csv(ROOT/'data/processed/strekningar.csv').sort_values('strekning_id').reset_index(drop=True)
segments=pd.read_csv(ROOT/'data/processed/vegsegment.csv')
tr=Transformer.from_crs(CRS.from_epsg(5973).sub_crs_list[0],25833,always_xy=True)
geo=Transformer.from_crs(4326,25833,always_xy=True)
lines=[]
for sid,group in segments.groupby('strekning_id',sort=True):
    lines.append(transform(tr.transform,shapely.union_all(shapely.force_2d(shapely.from_wkt(group.geometri_wkt.to_numpy())))))
assert len(lines)==len(roads)
tree=shapely.STRtree(lines)
results=[]
for _,row in df.iterrows():
    point=shapely.Point(row.anchor_x_25833,row.anchor_y_25833)
    candidates=tree.query(point,predicate='dwithin',distance=100)
    ranked=sorted((point.distance(lines[j]),j) for j in candidates if roads.iloc[j].vegkategori==row.vegkategori)
    sid=None; number=None; distance=np.nan; reason='no_same_category_within_100m'; coarse=False
    if ranked:
        distance,j=ranked[0]
        if len(ranked)>1 and ranked[1][0]-distance<20:
            reason='ambiguous'
        else:
            sid=roads.iloc[j].strekning_id
            number=int(roads.iloc[j].vegnummer)
            reason='unique_same_category_geometric_candidate'
            for a,b in [('START_X','START_Y'),('END_X','END_Y')]:
                if pd.notna(row[a]) and pd.notna(row[b]):
                    x,y=geo.transform(float(row[a]),float(row[b]))
                    if np.isfinite(x) and np.isfinite(y) and shapely.Point(x,y).distance(lines[j])>100:
                        coarse=True
    results.append(dict(row_id=row.row_id,diagnostic_sid=sid,diagnostic_number=number,
                        diagnostic_distance_m=distance,diagnostic_coarse=coarse,diagnostic_reason=reason))
diag=df.merge(pd.DataFrame(results),on='row_id',validate='one_to_one')
diag['possible_renumbering']=(diag.strekning_id.isna() & diag.diagnostic_sid.notna()
                             & diag.vegnummer.ne(diag.diagnostic_number))
diag['recoverable_strict_candidate']=diag.possible_renumbering & ~diag.diagnostic_coarse
diag['year']=diag.dato.dt.year
annual=diag.groupby('year').agg(explicit_slide_rows=('row_id','size'),original_matched=('strekning_id','count'),
    geometric_candidates_without_number=('diagnostic_sid','count'),potential_renumbered_rows=('possible_renumbering','sum'),
    potential_strict_additional_rows=('recoverable_strict_candidate','sum'))
annual.to_csv(OUT/'arskontroll.csv',encoding='utf-8-sig')
diag.to_parquet(OUT/'radkontroll.parquet',index=False)
examples=diag.loc[diag.recoverable_strict_candidate].groupby(['vegkategori','vegnummer','diagnostic_number']).agg(
    message_rows=('row_id','size'),first_date=('dato','min'),example_name=('NAME','first')).reset_index().sort_values('message_rows',ascending=False)
examples.to_csv(OUT/'gamle_nye_nummer_kandidatar.csv',index=False,encoding='utf-8-sig')
summary=[]
for label,mask in [('2013_2020',diag.year.le(2020)),('2021_2026',diag.year.ge(2021))]:
    g=diag.loc[mask]
    summary.append(dict(period=label,explicit_slide_rows=len(g),original_matched=int(g.strekning_id.notna().sum()),
        geometric_without_number=int(g.diagnostic_sid.notna().sum()),
        additional_possible_renumbered=int(g.possible_renumbering.sum()),
        additional_strict_candidates=int(g.recoverable_strict_candidate.sum())))
report=dict(summary=summary,method='Same-category spatial ablation: only road-number equality removed; 100m and 20m ambiguity rules retained',
    qualification='Potential renumberings, not validated historical road matches; no production labels changed',
    limits=['Current geometry still used','No category changes resolved','Current numbers may coincide with old numbers elsewhere',
            'Message rows are not independent slides or positive section-days','Only explicit-slide study candidates analysed'])
(OUT/'rapport.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
print(examples.head(12).to_string(index=False))
