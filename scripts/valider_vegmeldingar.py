"""Meaningful boundary cases and independent checks of persisted message labels."""
import gzip
import hashlib
import json
from pathlib import Path
import pandas as pd
from filtrer_xgeo_vegmeldingar import classify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/processed/vegmeldingar'
cases = {
    'Stengt på grunn av snøras.':'meldt_skred',
    'Stengt på grunn av fare for ras.':'skredfare',
    'Fare for steinskred/steinsprang, vegen er stengt.':'skredfare',
    'Stengt på grunn av snøras og fare for ras.':'meldt_skred',
    'Steinskred/steinsprang.|Merk at sluttiden er usikker og kan endres.':'meldt_skred',
    'Åpen for trafikk etter snøras.':'opning_etter_skred',
    'Kontrollert utløsning av snøskred.':'kontrollert_skred',
    'Mulig jordskred, vegen er stengt.':'uavklart',
    'Ingen skred observert.':'uavklart',
    'Stengt på grunn av uvær.':'anna',
    'Flom, vegen er stengt.':'anna',
    'Isnedfall, ett stengt kjørefelt.':'meldt_skred',
}
for text,expected in cases.items():
    assert classify(text)[0] == expected,(text,classify(text),expected)
manifest = json.loads((ROOT/'data/raw/xgeo_vegmeldingar/manifest.json').read_text())
assert manifest['complete']
count = 0
for year in manifest['years']:
    rows = 0
    for page in year['pages']:
        file = ROOT/'data/raw/xgeo_vegmeldingar'/page['file']
        payload = file.read_bytes()
        assert hashlib.sha256(payload).hexdigest()==page['sha256']
        data = json.loads(gzip.decompress(payload))
        assert len(data['features']) == page['rows']
        rows += page['rows']
    assert rows == year['rows'] == year['count_before'] == year['count_after']
    count += rows
assert count == manifest['rows']
d = pd.read_parquet(OUT/'meldingar_vestland_kandidatar.parquet')
e = pd.read_parquet(OUT/'skredepisodar_kandidatar.parquet')
assert d.row_id.is_unique and e.episode_id.is_unique
strict = e.loc[e.strict_candidate]
first = strict.merge(d[['row_id','strict_row','dato','strekning_id']],left_on='first_row_id',right_on='row_id',suffixes=('','_row'),validate='many_to_one')
assert first.strict_row.all()
assert first.dato.eq(first.dato_row).all()
assert first.strekning_id.eq(first.strekning_id_row).all()
positive_rows = d.loc[d.strict_row]
assert positive_rows.klasse.eq('meldt_skred').all()
assert (~positive_rows.grovt_stadfesta).all()
assert positive_rows.avstand_m.le(100).all()
assert (~positive_rows.date_utc_missing).all()
assert positive_rows.dato.between('2013-01-01','2026-10-03').all()
counts = strict.groupby(['strekning_id','dato']).episode_id.nunique().sort_index()
daily = pd.read_parquet(OUT/'vegmelding_skred_dogn.parquet').set_index(['strekning_id','dato']).sort_index()
pd.testing.assert_series_equal(counts,daily.melde_skred_episodar,check_names=False)
total_positives = 0
for year in range(2013,2027):
    panel = pd.read_parquet(OUT/f'etikettar_dogn/{year}.parquet')
    original = pd.read_parquet(ROOT/f'data/weather/strekning_dogn/{year}.parquet',columns=['strekning_id','dato','registrert_skred'])
    pd.testing.assert_frame_equal(panel[original.columns],original)
    assert not panel.duplicated(['strekning_id','dato']).any()
    assert panel.vegmelding_skred.eq(panel.melde_skred_episodar.gt(0)).all()
    assert panel.skred_ei_av_kjeldene.eq(panel[['registrert_skred','vegmelding_skred']].max(axis=1)).all()
    total_positives += int(panel.vegmelding_skred.sum())
assert total_positives == len(daily)
result = dict(validated=True,raw_rows=count,strict_episode_candidates=len(strict),
              positive_section_days=total_positives,classifier_boundary_cases=len(cases),
              checks=['Raw page hashes/counts', 'Risk vs actual/uncertain/controlled/opening text cases',
                      'Episode first row alignment', 'Strict spatial/date rules',
                      'Daily counts independently recomputed', 'Original labels retained in all yearly panels'],
              qualification='Technical checks passed; does not validate semantic accuracy or historical coverage')
(OUT/'validation_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
