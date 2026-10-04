"""Official reform aliases, with old county and explicit transition policy.

Xgeo has no hp/metres: split aliases are resolved spatially by the caller.
NVDB changed-date is NOT a road-reference validity boundary. Allow old aliases
until 2021-12-31, recording post-change use; later aliases remain review-only.
"""
import hashlib
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT/'data/raw/historiske_vegnummer'
TRANSITION_END = pd.Timestamp('2021-12-31')
MUNICIPALITY_SOURCE = 'https://www.regjeringen.no/no/tema/kommuner-og-regioner/kommunestruktur/nyekommuneogfylkesnummer/id2629203/'


def old_county(municipality):
    municipality = int(municipality)
    if municipality == 4601 or 4611 <= municipality <= 4634:
        return 12
    if municipality == 4602 or 4635 <= municipality <= 4651:
        return 14
    raise ValueError(f'Unknown Vestland municipality: {municipality}')


def load_crosswalk():
    sources = {s['county']: s for s in json.loads((RAW/'sources.json').read_text(encoding='utf-8'))}
    records = []
    for county in (12,14):
        source = sources[county]
        assert hashlib.sha256((RAW/source['file']).read_bytes()).hexdigest() == source['sha256']
        pages = json.loads((RAW/f'F{county}_tables.json').read_text(encoding='utf-8'))
        for page_number, tables in enumerate(pages,1):
            for table in tables:
                for row_number, row in enumerate(table,1):
                    if row[0] != str(county):
                        continue
                    assert len(row) == 11 and row[2].isdigit() and row[8] == 'Vedtatt', row
                    # Two old FV573 pieces became private roads, outside ERF study.
                    if row[6] == 'PV':
                        continue
                    assert row[6].isdigit(), row
                    records.append(dict(crosswalk_id=f'F{county}:p{page_number}:r{row_number}',
                        old_county=county,vegkategori=row[1],old_number=int(row[2]),new_number=int(row[6]),
                        old_hp=row[3],old_from_meter=row[4],old_to_meter=row[5],description=row[7],
                        nvdb_changed_date=pd.to_datetime(row[9],format='%d.%m.%Y'),note=row[10],
                        source_url=source['url'],source_sha256=source['sha256']))
    crosswalk = pd.DataFrame(records)
    assert len(crosswalk) == 675
    return crosswalk


def alias_records(crosswalk):
    result = {}
    for record in crosswalk.to_dict('records'):
        if record['old_number'] != record['new_number']:
            key = (record['old_county'],record['vegkategori'],record['old_number'],record['new_number'])
            result.setdefault(key,[]).append(record)
    return result


def select_evidence(aliases, county, category, old_number, new_number, date):
    if pd.isna(date) or date > TRANSITION_END or pd.isna(old_number):
        return []
    return aliases.get((county,category,int(old_number),int(new_number)),[])
