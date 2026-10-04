"""Stream supplied NVE GeoJSON archive and intersect current road lines."""
import hashlib
import json
import zipfile
from pathlib import Path
from collections import defaultdict
import ijson
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from pyproj import CRS, Transformer
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/aktsomhet'
LAYERS = {
    'jord_flaum': ['Skred_JordFlomAktsomhetOmr'],
    'stein': ['Skred_SteinsprangAktsomhet_UtlopOmr', 'Skred_SteinsprangAktsomhet_UtlosningOmr'],
    'sno_s2_utan_skog': ['Skred_SnoAktsomhet_S2'],
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    archive = ROOT / 'data/raw/nve/NVE_47551B14_1791106303286_10540.zip'
    segments = pd.read_csv(ROOT / 'data/processed/vegsegment.csv')
    assert set(segments.srid) == {5973}
    transformer = Transformer.from_crs(CRS.from_epsg(5973).sub_crs_list[0], 25833, always_xy=True)
    ids, lines = [], []
    for sid, group in segments.groupby('strekning_id', sort=True):
        ids.append(sid)
        line = shapely.union_all(shapely.force_2d(shapely.from_wkt(group.geometri_wkt.to_numpy())))
        lines.append(transform(transformer.transform, line))
    tree = shapely.STRtree(lines)
    table = pd.DataFrame({'strekning_id': ids, 'geometrisk_veglengde_m': [g.length for g in lines]})
    all_clips = [[] for _ in ids]
    layer_audit = []
    with zipfile.ZipFile(archive) as z:
        for theme, names in LAYERS.items():
            clips = [[] for _ in ids]
            hit = np.zeros(len(ids), dtype=bool)
            nearby = hit.copy()
            for name in names:
                member = f'NVEKartdata/NVEData/{name}.geojson'
                # Header CRS is explicit: GeoJSON is not lon/lat here.
                with z.open(member) as stream:
                    crs = next(ijson.items(stream, 'crs.properties.name'))
                assert crs == 'EPSG:25833', crs
                digest = hashlib.sha256()
                with z.open(member) as stream:
                    while chunk := stream.read(1024*1024):
                        digest.update(chunk)
                count = repaired = matched = 0
                properties = None
                with z.open(member) as stream:
                    for feature in ijson.items(stream, 'features.item', use_float=True):
                        count += 1
                        if properties is None:
                            properties = feature['properties']
                        polygon = shape(feature['geometry'])
                        assert polygon.geom_type in ['Polygon', 'MultiPolygon']
                        if not polygon.is_valid:
                            polygon = shapely.make_valid(polygon)
                            repaired += 1
                        near = tree.query(polygon, predicate='dwithin', distance=20)
                        nearby[near] = True
                        candidates = tree.query(polygon, predicate='intersects')
                        if len(candidates):
                            matched += 1
                        for index in candidates:
                            hit[index] = True
                            # Intersect once after union, avoiding floating-point
                            # duplication of separately clipped line fragments.
                            clips[index].append(polygon)
                        if count % 20000 == 0:
                            print(f'{name}: {count} polygon', flush=True)
                layer_audit.append(dict(member=member, sha256=digest.hexdigest(), crs=crs,
                    polygons=count, repaired=repaired, polygons_intersecting_roads=matched,
                    first_feature_properties=properties))
                print(f'Fullført {name}: {count} polygon', flush=True)
            lengths = np.array([lines[i].intersection(shapely.union_all(parts)).length if parts else 0
                                for i, parts in enumerate(clips)])
            table[theme+'_overlapp_m'] = lengths
            table[theme+'_andel'] = lengths / table.geometrisk_veglengde_m
            table[theme+'_treff'] = hit
            table[theme+'_innan20m'] = nearby
            for index, parts in enumerate(clips):
                all_clips[index].extend(parts)
            assert (table[theme+'_andel'].between(0, 1+1e-8)).all()
    table['alle_overlapp_m'] = [lines[i].intersection(shapely.union_all(parts)).length if parts else 0
                               for i, parts in enumerate(all_clips)]
    table['alle_andel'] = table.alle_overlapp_m / table.geometrisk_veglengde_m
    table['behald_direkte'] = table[[t+'_treff' for t in LAYERS]].any(axis=1)
    table['behald_innan20m'] = table[[t+'_innan20m' for t in LAYERS]].any(axis=1)
    assert table.strekning_id.is_unique and len(table) == 957
    assert table.alle_andel.between(0, 1+1e-8).all()
    table.to_csv(OUT / 'strekning_aktsomhet.csv', index=False, encoding='utf-8-sig')
    table.to_parquet(OUT / 'strekning_aktsomhet.parquet', index=False)
    table.loc[~table.behald_direkte].to_csv(OUT / 'strekningar_utan_direkte_treff.csv', index=False, encoding='utf-8-sig')
    # Audit exclusions using unique event/section links, NOT duplicate reference rows.
    links = pd.read_csv(ROOT / 'data/processed/skred_strekning.csv')
    slides = pd.read_csv(ROOT / 'data/processed/skred.csv', parse_dates=['dato'])
    joined = links[['skred_id', 'strekning_id']].drop_duplicates().merge(
        slides[['skred_id', 'dato', 'skredtype']], on='skred_id', validate='many_to_one').merge(
        table, on='strekning_id', validate='many_to_one')
    joined.loc[~joined.behald_direkte].to_csv(OUT / 'skred_pa_strekningar_utan_treff.csv', index=False, encoding='utf-8-sig')
    counts = joined.groupby(['skredtype', 'behald_direkte']).agg(
        unike_hendingar=('skred_id', 'nunique'), hending_strekning_koplingar=('skred_id', 'size')).reset_index()
    counts.to_csv(OUT / 'skredtype_filterkontroll.csv', index=False, encoding='utf-8-sig')
    summaries = []
    periods = [('alle_20aar', joined), ('trening_2013_2020', joined.loc[joined.dato.between('2013-01-01', '2020-12-31')]),
               ('sluttest_2024_2026', joined.loc[joined.dato >= '2024-01-01'])]
    for period, frame in periods:
        for rule in ['behald_direkte', 'behald_innan20m']:
            removed = frame.loc[~frame[rule]]
            summaries.append(dict(period=period, rule=rule,
                sections_retained=int(table[rule].sum()), sections_removed=int((~table[rule]).sum()),
                unique_events_on_removed_sections=int(removed.skred_id.nunique()),
                events_only_on_removed_sections=int(len(set(removed.skred_id)-set(frame.loc[frame[rule], 'skred_id']))),
                event_section_links_removed=len(removed),
                positive_section_days_removed=len(removed[['strekning_id','dato']].drop_duplicates()),
                positive_section_days_total=len(frame[['strekning_id','dato']].drop_duplicates())))
    report = dict(archive=archive.relative_to(ROOT).as_posix(), archive_sha256=hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest(),
        crs='EPSG:25833', themes=LAYERS, layers=layer_audit, summaries=summaries,
        method='Exact road-line intersection with local polygon union prevents double counting overlapping polygons. Touch-only intersections retained.',
        length_denominator='Length of union of current road line geometries, not sum of NVDB segment length fields.',
        tolerance='20m is a separate sensitivity rule, not a mapped hazard boundary or positional accuracy estimate.',
        limitations=['Current 2026 extract, not historical hazard maps', 'All target slide types retained; map coverage differs by process',
                     'No roads removed from original datasets', 'Events on a retained section are not necessarily located inside a polygon',
                     'Road arms, parallel lines, ferries and tunnels have not been separated',
                     'Snow S2 without forest selected; S3 and forest-effect alternatives not analysed',
                     'No model retrained; test labels only used for reporting exclusions'])
    (OUT / 'rapport.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == '__main__':
    main()
