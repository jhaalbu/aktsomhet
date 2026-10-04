"""Check reform edge cases and audit actual changed matches/positive days."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from historiske_vegnummer import load_crosswalk, alias_records, select_evidence, old_county

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/processed/vegmeldingar'
BEFORE = ROOT/'data/processed/vegmeldingar_foer_historisk'
crosswalk = load_crosswalk()
aliases = alias_records(crosswalk)
date = pd.Timestamp('2015-01-01')
# Published examples, including a split road, same number in two old counties,
# a riksveg change, and stale-number policy. These are not synthetic road labels.
assert select_evidence(aliases,14,'F',241,5623,date)
assert not select_evidence(aliases,12,'F',241,5623,date)
assert select_evidence(aliases,14,'F',152,5606,date)[0]['old_hp'] == '4'
assert select_evidence(aliases,14,'F',152,5617,date)[0]['old_hp'] == '1'
assert select_evidence(aliases,12,'F',7,49,date)
assert select_evidence(aliases,12,'F',7,79,date)
assert not select_evidence(aliases,14,'F',7,49,date)
assert select_evidence(aliases,14,'R',55,13,date)
assert not select_evidence(aliases,14,'F',55,13,date)
assert not select_evidence(aliases,14,'F',241,5623,pd.Timestamp('2022-01-01'))
assert not select_evidence(aliases,14,'F',241,5623,pd.NaT)
assert old_county(4634)==12 and old_county(4635)==14 and old_county(4602)==14

after = pd.read_parquet(OUT/'meldingar_vestland_kandidatar.parquet')
before = pd.read_parquet(BEFORE/'meldingar_vestland_kandidatar.parquet')
historical = after.loc[after.historisk_omnummerering]
roads = pd.read_csv(ROOT/'data/processed/strekningar.csv').set_index('strekning_id')
assert historical.avstand_m.le(100).all()
assert historical.kopling_margin_m.ge(20).all()
assert historical.vegnummer.ne(historical.kopla_vegnummer).all()
assert historical.dato.le(pd.Timestamp('2021-12-31')).all()
assert historical.vegkategori.eq(historical.strekning_id.map(roads.vegkategori)).all()
assert historical.kopla_vegnummer.eq(historical.strekning_id.map(roads.vegnummer)).all()
for row in historical.itertuples():
    expected = select_evidence(aliases,int(row.historisk_fylke),row.vegkategori,row.vegnummer,row.kopla_vegnummer,row.dato)
    assert expected and set(row.nummeroversikt_rader.split('|')) == {r['crosswalk_id'] for r in expected}
    assert row.nummeroversikt_kjelde == expected[0]['source_url']

# Original source identifiers and road reference are retained for every row.
pd.testing.assert_frame_equal(before.set_index('row_id')[['ROAD_TYPE','ROAD_NUMBER','dato','NAME']].sort_index(),
                              after.set_index('row_id')[['ROAD_TYPE','ROAD_NUMBER','dato','NAME']].sort_index())
rows = before[['row_id','strekning_id','strict_row']].merge(after,on='row_id',suffixes=('_before',''),validate='one_to_one')
changed = rows.strekning_id_before.fillna('').ne(rows.strekning_id.fillna(''))
rows['change'] = np.select([
    rows.strekning_id_before.isna() & rows.strekning_id.notna(),
    rows.strekning_id_before.notna() & rows.strekning_id.isna(),
    rows.strekning_id_before.notna() & rows.strekning_id.notna() & changed],
    ['new_match','removed_match','reassigned_match'],default='unchanged')
rows.loc[changed].to_csv(OUT/'historiske_koplingsendringar.csv',index=False,encoding='utf-8-sig')

old_daily = pd.read_parquet(BEFORE/'vegmelding_skred_dogn.parquet')[['strekning_id','dato']]
new_daily = pd.read_parquet(OUT/'vegmelding_skred_dogn.parquet')[['strekning_id','dato']]
changes = old_daily.merge(new_daily,on=['strekning_id','dato'],how='outer',indicator=True,validate='one_to_one')
changes.to_csv(OUT/'historiske_dognendringar.csv',index=False,encoding='utf-8-sig')
annual = changes.assign(year=changes.dato.dt.year).groupby('year').agg(
    before_positive_days=('_merge',lambda x:int(x.ne('right_only').sum())),
    after_positive_days=('_merge',lambda x:int(x.ne('left_only').sum())),
    added_positive_days=('_merge',lambda x:int(x.eq('right_only').sum())),
    removed_positive_days=('_merge',lambda x:int(x.eq('left_only').sum())))
annual['net_change'] = annual.after_positive_days-annual.before_positive_days
annual.to_csv(OUT/'historisk_kopling_per_ar.csv',encoding='utf-8-sig')
result = dict(validated=True,official_crosswalk_rows=len(crosswalk),historically_linked_rows=len(historical),
    historical_strict_rows=int(historical.strict_row.sum()),
    message_changes=rows.change.value_counts().to_dict(),
    before_positive_days=len(old_daily),after_positive_days=len(new_daily),
    added_positive_days=int(changes._merge.eq('right_only').sum()),
    removed_positive_days=int(changes._merge.eq('left_only').sum()),
    annual=annual.reset_index().to_dict('records'),
    qualification='Crosswalk and linkage rules checked; current geometry and missing hp/metres still limit event-location certainty')
(OUT/'historisk_validering.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
