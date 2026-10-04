"""Independent checks of persisted hazard features and exclusion counts."""
import json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / 'data/processed/aktsomhet'
table = pd.read_parquet(out / 'strekning_aktsomhet.parquet')
csv = pd.read_csv(out / 'strekning_aktsomhet.csv')
pd.testing.assert_frame_equal(csv, table, check_dtype=False, rtol=1e-10)
roads = pd.read_csv(ROOT / 'data/processed/strekningar.csv')
assert table.strekning_id.is_unique
assert set(table.strekning_id) == set(roads.strekning_id)
themes = ['stein', 'jord_flaum', 'sno_s2_utan_skog']
for theme in themes + ['alle']:
    assert table[theme+'_andel'].between(0, 1+1e-8).all()
    np.testing.assert_allclose(table[theme+'_overlapp_m'], table[theme+'_andel']*table.geometrisk_veglengde_m)
for theme in themes:
    assert (table.alle_overlapp_m + 1e-6 >= table[theme+'_overlapp_m']).all()
    assert (table[theme+'_innan20m'] | ~table[theme+'_treff']).all()
assert (table.alle_overlapp_m <= table[[t+'_overlapp_m' for t in themes]].sum(axis=1)+1e-6).all()
assert table.behald_direkte.eq(table[[t+'_treff' for t in themes]].any(axis=1)).all()
events = pd.read_csv(ROOT / 'data/processed/skred_strekning.csv', parse_dates=['dato'])
events = events[['skred_id', 'strekning_id', 'dato']].drop_duplicates()
assert len(events) == 16262
events = events.merge(table[['strekning_id', 'behald_direkte', 'behald_innan20m']],
                      how='left', on='strekning_id', validate='many_to_one')
assert events.behald_direkte.notna().all()
report = json.loads((out / 'rapport.json').read_text(encoding='utf-8'))
for summary in report['summaries']:
    subset = events
    if summary['period'] == 'trening_2013_2020':
        subset = events.loc[events.dato.between('2013-01-01', '2020-12-31')]
    if summary['period'] == 'sluttest_2024_2026':
        subset = events.loc[events.dato >= '2024-01-01']
    removed = subset.loc[~subset[summary['rule']]]
    assert len(removed) == summary['event_section_links_removed']
    assert len(removed[['strekning_id', 'dato']].drop_duplicates()) == summary['positive_section_days_removed']
    assert len(subset[['strekning_id', 'dato']].drop_duplicates()) == summary['positive_section_days_total']
excluded = pd.read_csv(out / 'skred_pa_strekningar_utan_treff.csv', parse_dates=['dato'])
assert set(zip(excluded.skred_id, excluded.strekning_id)) == set(zip(
    events.loc[~events.behald_direkte, 'skred_id'], events.loc[~events.behald_direkte, 'strekning_id']))
validation = dict(validated=True, sections=len(table), event_section_links=len(events),
    checks=['CSV/Parquet agreement', 'Complete unique road keys', 'Overlap fractions and union bounds',
            'Direct hits included within 20m', 'Exclusion counts independently recomputed', 'Excluded event list'])
(out / 'validation_report.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
print(json.dumps(validation, indent=2))
