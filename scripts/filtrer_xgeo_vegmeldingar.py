"""Conservative, auditable message labels, current-road matches and episode candidates."""
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path
import numpy as np
import pandas as pd
import shapely
from pyproj import CRS, Transformer
from shapely.ops import transform
from historiske_vegnummer import load_crosswalk, alias_records, old_county, select_evidence, TRANSITION_END

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/xgeo_vegmeldingar'
OUT = ROOT / 'data/processed/vegmeldingar'


def normal(text):
    if pd.isna(text):
        return ''
    return re.sub(r'\s+', ' ', str(text).lower().translate(str.maketrans({'ø':'o','å':'a','æ':'ae'}))).strip()


TOKEN = r'\b(?:(?:sno|stein|jord|flom|sorpe|is)?(?:skred|ras)|steinsprang|steinnedfall|isnedfall)\b'


def classify(text):
    s = normal(text)
    if re.search(r'skredkontroll|kontrollert.{0,20}(skred|ras)|(?:spreng|utlosning).{0,30}(skred|ras)|(?:skred|ras).{0,30}spreng', s):
        return 'kontrollert_skred', 'controlled_release'
    if re.search(r'\b(?:ingen|ikke|ikkje)\s+(?:noe|noko|nye|nytt)?\s*'+TOKEN, s):
        return 'uavklart', 'negated_slide_reference'
    # Remove risk references locally: an actual slide and further risk may coexist.
    compound = TOKEN+r'(?:\s*/\s*'+TOKEN+r')*'
    stripped = re.sub(r'\b(?:fare|risiko)\s+for\s+(?:nye\s+)?'+compound, '', s)
    stripped = re.sub(r'\b(?:rasfare|skredfare)\b', '', stripped)
    actual = re.search(TOKEN, stripped) is not None
    risk = bool(re.search(r'(?:fare|risiko)\s+for.{0,20}(?:ras|skred)|rasfare|skredfare', s))
    if actual:
        if re.search(r'\b(?:mulig|mogleg|mistanke om|kan (?:komme|ga|forekomme)|potensielt|ventet|venta|varslet)\s+(?:et |eit |nye |nytt )?'+TOKEN, stripped):
            return 'uavklart', 'possible_or_forecast_slide'
        if re.search(r'\b(?:apen|opna|gjenapnet|gjenopna)\b|apnet for trafikk', s):
            return 'opning_etter_skred', 'opening_does_not_date_onset'
        return 'meldt_skred', 'explicit_slide_word_without_risk_only'
    if risk:
        return 'skredfare', 'risk_only'
    return 'anna', 'no_explicit_actual_slide'


def parse_time(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return pd.NaT
    if isinstance(value, (int,float)):
        return pd.to_datetime(value, unit='ms', utc=True, errors='coerce')
    return pd.to_datetime(value, utc=True, errors='coerce')


def review_and_years(df):
    data = df.copy()
    data['year'] = data.dato.dt.year
    review = pd.concat([g.sample(n=min(8,len(g)),random_state=20261004)
                        for _,g in data.groupby(['year','klasse','strict_row'])],ignore_index=True)
    review['review_label'] = ''
    review['review_comment'] = ''
    review.to_csv(OUT/'manuell_kontroll.csv',index=False,encoding='utf-8-sig')
    data['explicit_slide'] = data.klasse.eq('meldt_skred')
    data['explicit_slide_matched'] = data.explicit_slide & data.strekning_id.notna()
    data['explicit_slide_coarse'] = data.explicit_slide & data.grovt_stadfesta
    annual = data.groupby('year').agg(candidate_rows=('row_id','size'),
        explicit_slide_rows=('explicit_slide','sum'),matched_explicit_slide_rows=('explicit_slide_matched','sum'),
        coarse_explicit_slide_rows=('explicit_slide_coarse','sum'),strict_message_rows=('strict_row','sum'))
    annual.to_csv(OUT/'filtersteg_per_ar.csv',encoding='utf-8-sig')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # One immutable pre-correction snapshot; repeat runs keep the same baseline.
    backup = ROOT/'data/processed/vegmeldingar_foer_historisk'
    if not backup.exists() and (OUT/'filterrapport.json').exists():
        shutil.copytree(OUT,backup,ignore=shutil.ignore_patterns('vegnummer_diagnose'))
    crosswalk = load_crosswalk()
    aliases = alias_records(crosswalk)
    crosswalk.to_csv(OUT/'historiske_nummeroversikt.csv',index=False,encoding='utf-8-sig')
    manifest = json.loads((RAW/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['complete']
    records = []
    for year in manifest['years']:
        for page in year['pages']:
            file = RAW / page['file']
            assert hashlib.sha256(file.read_bytes()).hexdigest() == page['sha256']
            data = json.loads(gzip.decompress(file.read_bytes()))
            assert len(data['features']) == page['rows']
            assert data.get('spatialReference',{}).get('wkid') == 4326
            for feature in data['features']:
                attrs = feature['attributes']
                row = dict(attrs)
                row['raw_file'] = page['file']
                row['row_id'] = hashlib.sha256(json.dumps(feature,sort_keys=True).encode()).hexdigest()[:24]
                geom = feature.get('geometry') or {}
                row['geometry_x'], row['geometry_y'] = geom.get('x'), geom.get('y')
                records.append(row)
    df = pd.DataFrame(records)
    assert len(df) == manifest['rows'] and df.row_id.is_unique
    # Preserve original values; *_UTC takes priority. Fallback is not accepted as UTC evidence.
    df['from_utc'] = df.FROM_DATE_UTC.map(parse_time)
    df['created_utc'] = df.DATEX_CREATE_DATE_UTC.map(parse_time)
    df['version_utc'] = df.DATEX_VERSION_DATE_UTC.map(parse_time)
    df['date_utc_missing'] = df.from_utc.isna()
    df['dato'] = df.from_utc.dt.tz_convert('Europe/Oslo').dt.tz_localize(None).dt.normalize()
    df['text'] = df.MSG_DESCRIPTION.fillna('')+' '+df.FREE_TEXT.fillna('')
    classes = df.text.map(classify)
    df['klasse'] = [x[0] for x in classes]
    df['regel'] = [x[1] for x in classes]
    df['vegkategori'] = df.ROAD_TYPE.map(lambda s: normal(s)[:1].upper() if normal(s) else '')
    df['vegnummer'] = pd.to_numeric(df.ROAD_NUMBER,errors='coerce')
    # Build section geometry once; a nearest road alone is NOT enough for a match.
    roads = pd.read_csv(ROOT/'data/processed/strekningar.csv').sort_values('strekning_id').reset_index(drop=True)
    segments = pd.read_csv(ROOT/'data/processed/vegsegment.csv')
    assert set(segments.srid) == {5973}
    tr = Transformer.from_crs(CRS.from_epsg(5973).sub_crs_list[0],25833,always_xy=True)
    lines = []
    county_lines = []
    for sid in roads.strekning_id:
        group = segments.loc[segments.strekning_id.eq(sid)]
        line = shapely.union_all(shapely.force_2d(shapely.from_wkt(group.geometri_wkt.to_numpy())))
        projected = transform(tr.transform,line)
        lines.append(projected)
        group = group.assign(old_county=group.kommune.map(old_county))
        by_county = {}
        for county,g in group.groupby('old_county'):
            by_county[int(county)] = projected if len(g)==len(group) else transform(tr.transform,
                shapely.union_all(shapely.force_2d(shapely.from_wkt(g.geometri_wkt.to_numpy()))))
        county_lines.append(by_county)
    tree = shapely.STRtree(lines)
    geo = Transformer.from_crs(4326,25833,always_xy=True)
    xs = pd.to_numeric(df.SHOW_X,errors='coerce').fillna(pd.to_numeric(df.geometry_x,errors='coerce'))
    ys = pd.to_numeric(df.SHOW_Y,errors='coerce').fillna(pd.to_numeric(df.geometry_y,errors='coerce'))
    valid = xs.between(-180,180) & ys.between(-90,90)
    east,north = geo.transform(xs.where(valid,np.nan).to_numpy(),ys.where(valid,np.nan).to_numpy())
    df['anchor_x_25833'],df['anchor_y_25833'] = east,north
    points = shapely.points(east,north)
    pairs = tree.query(points,predicate='dwithin',distance=1000)
    candidates = {}
    for row,index in zip(*pairs):
        candidates.setdefault(int(row),[]).append(int(index))
    df['west_name'] = df.NAME.fillna('').str.contains('Vestland|Hordaland|Sogn og Fjordane',case=False,regex=True)
    df['near_study_road'] = df.index.isin(candidates)
    df['study_candidate'] = df.west_name | df.near_study_road
    matched_sid, distances, reasons, range_coarse = [],[],[],[]
    audit_rows = []
    for i,row in df.iterrows():
        sid, distance, reason, coarse = None,np.nan,'outside_study',False
        audit = dict(kopla_vegnummer=np.nan,historisk_omnummerering=False,historisk_fylke=np.nan,
                     nummeroversikt_rader='',nummeroversikt_kjelde='',nummer_endra_nvdb_dato='',
                     historisk_etter_nvdb_endring=False,historisk_datoregel='',
                     historisk_hp_meter_tilgjengeleg=False,kopling_margin_m=np.nan)
        if row.study_candidate:
            reason = 'no_same_road_within_100m'
            matches = []
            evidence_by_index = {}
            for j in candidates.get(i,[]):
                road = roads.iloc[j]
                if road.vegkategori != row.vegkategori:
                    continue
                dist = points[i].distance(lines[j])
                if dist > 100:
                    continue
                if road.vegnummer == row.vegnummer:
                    matches.append((dist,j))
                    continue
                counties = sorted((points[i].distance(line),county) for county,line in county_lines[j].items())
                if len(counties)>1 and counties[1][0]-counties[0][0]<20:
                    continue
                evidence = select_evidence(aliases,counties[0][1],row.vegkategori,row.vegnummer,road.vegnummer,row.dato)
                if evidence:
                    matches.append((dist,j))
                    evidence_by_index[j] = (counties[0][1],evidence)
            ranked = sorted(matches)
            if ranked and ranked[0][0] <= 100:
                distance,j = ranked[0]
                if len(ranked)>1 and ranked[1][0]-distance < 20:
                    reason = 'ambiguous_section_boundary'
                else:
                    sid,reason = roads.iloc[j].strekning_id,'same_road_nearest_unique'
                    audit['kopla_vegnummer'] = int(roads.iloc[j].vegnummer)
                    audit['kopling_margin_m'] = ranked[1][0]-distance if len(ranked)>1 else np.inf
                    if j in evidence_by_index:
                        county,evidence = evidence_by_index[j]
                        changed_dates = sorted({r['nvdb_changed_date'] for r in evidence})
                        audit.update(historisk_omnummerering=True,historisk_fylke=county,
                            nummeroversikt_rader='|'.join(r['crosswalk_id'] for r in evidence),
                            nummeroversikt_kjelde=evidence[0]['source_url'],
                            nummer_endra_nvdb_dato='|'.join(d.strftime('%Y-%m-%d') for d in changed_dates),
                            historisk_etter_nvdb_endring=bool(row.dato>=min(changed_dates)),
                            historisk_datoregel='old_alias_allowed_through_2021_geographically_validated')
                        reason = 'official_historical_number_nearest_unique'
                    # Long closure ranges can span several sections. Do not assign all
                    # of them to a slide from an arbitrary display point.
                    endpoints = []
                    for a,b in [('START_X','START_Y'),('END_X','END_Y')]:
                        if pd.notna(row[a]) and pd.notna(row[b]):
                            px,py = geo.transform(float(row[a]),float(row[b]))
                            if np.isfinite(px) and np.isfinite(py):
                                endpoints.append(shapely.Point(px,py))
                    coarse = any(p.distance(lines[j]) > 100 for p in endpoints)
                    if coarse:
                        reason += '_but_range_extends_off_section'
        matched_sid.append(sid)
        distances.append(distance)
        reasons.append(reason)
        range_coarse.append(coarse)
        audit_rows.append(audit)
    df['strekning_id'],df['avstand_m'],df['koplingsregel'],df['grovt_stadfesta'] = matched_sid,distances,reasons,range_coarse
    df = pd.concat([df,pd.DataFrame(audit_rows,index=df.index)],axis=1)
    df = df.loc[df.study_candidate].copy()
    df['strict_row'] = (df.klasse.eq('meldt_skred') & df.strekning_id.notna() & ~df.grovt_stadfesta
                        & ~df.date_utc_missing & df.dato.between('2013-01-01','2026-10-03'))
    df['situation_key'] = df.EXT_SIT_NO.fillna('').astype(str)
    empty = df.situation_key.eq('')
    df.loc[empty,'situation_key'] = 'row:'+df.loc[empty,'row_id']
    # Episode candidates: same source situation and current section, split on a
    # >7 day gap. Source situations can be reused; this is a heuristic, not truth.
    positives = df.loc[df.klasse.eq('meldt_skred') & df.strekning_id.notna() & df.from_utc.notna()].copy()
    positives = positives.sort_values(['situation_key','strekning_id','from_utc','row_id'])
    group = positives.groupby(['situation_key','strekning_id'],sort=False)
    positives['episode_number'] = group.from_utc.diff().gt(pd.Timedelta(days=7)).groupby(
        [positives.situation_key,positives.strekning_id]).cumsum().astype(int)
    episodes = []
    for (situation,sid,num),g in positives.groupby(['situation_key','strekning_id','episode_number'],sort=False):
        first = g.iloc[0]
        eid = hashlib.sha256(f'{situation}|{sid}|{num}'.encode()).hexdigest()[:24]
        # Earliest positive date determines onset. Later valid updates may not
        # shift an invalid/coarse first report into a clean positive example.
        episodes.append(dict(episode_id=eid,situation_key=situation,strekning_id=sid,
            dato=first.dato,first_from_utc=first.from_utc,last_from_utc=g.from_utc.max(),
            message_rows=len(g),source_record_ids=g.EXT_REC_NO.nunique(),
            span_days=(g.from_utc.max()-first.from_utc).total_seconds()/86400,
            strict_candidate=bool(first.strict_row),first_row_id=first.row_id,
            first_text=first.text,any_coarse=bool(g.grovt_stadfesta.any()),
            timestamp_meaning='Earliest positive message validity start, not verified slide onset'))
        positives.loc[g.index,'episode_id'] = eid
    e = pd.DataFrame(episodes)
    df['episode_id'] = positives.episode_id.reindex(df.index)
    df.to_parquet(OUT/'meldingar_vestland_kandidatar.parquet',index=False)
    df.to_csv(OUT/'meldingar_vestland_kandidatar.csv',index=False,encoding='utf-8-sig')
    e.to_parquet(OUT/'skredepisodar_kandidatar.parquet',index=False)
    e.to_csv(OUT/'skredepisodar_kandidatar.csv',index=False,encoding='utf-8-sig')
    strict = e.loc[e.strict_candidate].copy()
    strict.to_csv(OUT/'skredepisodar_strengt_utval.csv',index=False,encoding='utf-8-sig')
    daily = strict.groupby(['strekning_id','dato']).agg(melde_skred_episodar=('episode_id','nunique')).reset_index()
    daily['vegmelding_skred'] = 1
    daily.to_parquet(OUT/'vegmelding_skred_dogn.parquet',index=False)
    # Do not overwrite original labels: expose competing outcomes for comparison.
    nvdb = pd.read_parquet(ROOT/'data/processed/skred_dogn.parquet')
    nvdb['dato'] = pd.to_datetime(nvdb.dato)
    nvdb = nvdb.loc[nvdb.dato.between('2013-01-01','2026-10-03')].copy()
    compare = nvdb.merge(daily,on=['strekning_id','dato'],how='outer',validate='one_to_one')
    compare['nvdb_skred'] = compare.registrerte_skred.notna().astype(int)
    compare['vegmelding_skred'] = compare.vegmelding_skred.fillna(0).astype(int)
    compare['skred_ei_av_kjeldene'] = compare[['nvdb_skred','vegmelding_skred']].max(axis=1)
    compare.to_parquet(OUT/'positive_dogn_kjeldesamanlikning.parquet',index=False)
    compare.to_csv(OUT/'positive_dogn_kjeldesamanlikning.csv',index=False,encoding='utf-8-sig')
    annual = compare.assign(year=compare.dato.dt.year).groupby('year').agg(
        nvdb_positive_dogn=('nvdb_skred','sum'),vegmelding_positive_dogn=('vegmelding_skred','sum'),
        union_positive_dogn=('skred_ei_av_kjeldene','sum'))
    annual['same_dato_strekning_begge'] = annual.nvdb_positive_dogn+annual.vegmelding_positive_dogn-annual.union_positive_dogn
    annual.to_csv(OUT/'kjeldesamanlikning_per_ar.csv',encoding='utf-8-sig')
    # Deterministic review samples for every class and acceptance status.
    review_and_years(df)
    # Build alternative label panels, preserving original weather and NVDB files.
    panel_folder = OUT / 'etikettar_dogn'
    panel_folder.mkdir(exist_ok=True)
    for year in range(2013,2027):
        panel = pd.read_parquet(ROOT/f'data/weather/strekning_dogn/{year}.parquet',
                                columns=['strekning_id','dato','registrert_skred'])
        labels = daily.loc[daily.dato.dt.year.eq(year)]
        panel = panel.merge(labels,on=['strekning_id','dato'],how='left',validate='one_to_one')
        panel['vegmelding_skred'] = panel.vegmelding_skred.fillna(0).astype(np.int8)
        panel['melde_skred_episodar'] = panel.melde_skred_episodar.fillna(0).astype(np.int16)
        panel['skred_ei_av_kjeldene'] = panel[['registrert_skred','vegmelding_skred']].max(axis=1).astype(np.int8)
        panel.to_parquet(panel_folder/f'{year}.parquet',index=False)
    report = dict(national_rows=len(records),study_candidate_rows=len(df),name_candidate_rows=int(df.west_name.sum()),
        spatial_candidate_rows=int(df.near_study_road.sum()),classes=df.klasse.value_counts().to_dict(),
        matched_rows=int(df.strekning_id.notna().sum()),coarse_matched_rows=int(df.grovt_stadfesta.sum()),
        strict_message_rows=int(df.strict_row.sum()),episode_candidates=len(e),strict_episode_candidates=len(strict),
        strict_positive_section_days=len(daily),same_day_both=int(((compare.nvdb_skred==1)&(compare.vegmelding_skred==1)).sum()),
        xgeo_only_positive_days=int(((compare.nvdb_skred==0)&(compare.vegmelding_skred==1)).sum()),
        nvdb_only_positive_days=int(((compare.nvdb_skred==1)&(compare.vegmelding_skred==0)).sum()),
        rules=dict(max_distance_m=100,ambiguity_margin_m=20,episode_gap_days=7,period=['2013-01-01','2026-10-03']),
        warnings=['Rule-based labels and episodes are unverified candidates; manual review required before model replacement',
                  'Same-day overlap is not a verified match between individual events',
                  'Missing message means no retained report, not absence of slides or verified monitoring coverage',
                  'Official reform aliases checked by old county and geometry through 2021; not exact dated hp/metre conversion',
                  'Later stale numbers, reclassification, earlier number changes and changed geometry can still miss historical roads',
                  'Geographic candidate selection uses nearby study roads OR county names, not an exact county polygon',
                  'No model trained; original NVDB outcome preserved'])
    report['historical_linkage'] = dict(crosswalk_rows=len(crosswalk),
        matched_message_rows=int(df.historisk_omnummerering.sum()),
        strict_message_rows=int((df.historisk_omnummerering & df.strict_row).sum()),
        transition_end=str(TRANSITION_END.date()),pre_correction_snapshot=str(backup))
    (OUT/'filterrapport.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
