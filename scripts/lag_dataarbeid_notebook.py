"""Build a standalone learning notebook for roads and Xgeo data preparation."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cells = []


def md(source):
    cells.append(dict(cell_type='markdown',metadata={},source=source.strip().splitlines(keepends=True)))


def code(source):
    cells.append(dict(cell_type='code',metadata={},source=source.strip().splitlines(keepends=True),execution_count=None,outputs=[]))


md('''# Dataarbeid: vegstrekningar og vegmeldingar i Vestland

Denne notebooken handlar berre om datagrunnlaget:

**NVDB-råsvar → segmenttabell → strekningsdatasett → kart → Xgeo-råsvar
→ tekstfilter → historisk vegkopling → episodar → berika streknings- og døgnstabellar.**

Køyr cellene ovanfrå og ned. Standardkøyringa bruker dei nedlasta rådataa,
byggjer vegtabellar på nytt i ei eiga mappe, viser filtreringsarbeidet og
eksporterer berika tabellar. Ingen vêrhenting eller modelltrening er med.

Vel prosjektet si `.venv` som Python-kjerne i VS Code eller Jupyter.
Pakkane står i `requirements-notebook.txt`. Om du bruker nettlesar-Jupyter:

```powershell
.venv/Scripts/python.exe -m pip install notebook
.venv/Scripts/python.exe -m notebook notebooks/vegnett_vegmeldingar_dataarbeid.ipynb
```

Last ned på nytt berre når du ønskjer eit nytt uttak. Endra vegnett kan krevje
at alle geografiske koplingar blir bygde på nytt. Resultata her gjeld
vegnettsuttaket frå 4. oktober 2026 og Xgeo-uttaket til og med 3. oktober 2026.
''')
code('''from pathlib import Path
import os, sys, json, gzip, hashlib, subprocess
ROOT = next((p for p in [Path.cwd(), *Path.cwd().parents]
             if (p / 'scripts/hent_nvdb.py').exists()), None)
assert ROOT is not None, 'Start frå prosjektmappa eller notebooks/'
sys.path.insert(0, str(ROOT / 'scripts'))
EXPORT = ROOT / 'data/notebook/vegnett_vegmeldingar'
EXPORT.mkdir(parents=True, exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(EXPORT / '.mplcache')
import numpy as np
import pandas as pd
import shapely
from shapely.ops import transform
from pyproj import CRS, Transformer
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from IPython.display import display

FETCH_NVDB = False             # True hentar eit nytt vegnettsuttak
FETCH_XGEO = False             # True hentar manglande Xgeo-år; fullførte år er cache
REBUILD_MESSAGE_LINKS = False  # True byggjer produksjonskopling og etikettar på nytt
YEAR = 2018                   # Året i den komplette demonstrasjons-døgnstabellen
SEED = 20261004

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def run_script(name, *args):
    subprocess.run([sys.executable, str(ROOT / 'scripts' / name), *args], cwd=ROOT, check=True)

print('Python:', sys.executable)
print('Eksportmappe:', EXPORT)
''')
md('''## 1. Hente og bevare vegnettet

NVDB-endepunktet gir **segment**, ikkje éi ferdig rad per vegstrekning.
Me ber om fylke 46, eksisterande europa-, riks- og fylkesvegar, og følgjer
API-et sin sidepeikar til heile uttaket er henta. Råsvara og ein manifestfil
med filter, tidspunkt og SHA-256-hashar blir bevart.

Den første sida er berre ein del av vegnettet. Koden viser førespurnaden,
og bruker heile det eksisterande uttaket når `FETCH_NVDB=False`.
Produksjonsskriptet har paginering og kontroll av alle sider.
''')
code('''from urllib.parse import urlencode
from hent_nvdb import ENDPOINT, download, build
nvdb_raw = ROOT / 'data/raw/nvdb'
print(ENDPOINT + '?' + urlencode(dict(fylke=46, vegsystemreferanse='EV,RV,FV', antall=1000)))
if FETCH_NVDB:
    download(nvdb_raw)
nvdb_manifest = read_json(nvdb_raw / 'manifest.json')
assert nvdb_manifest['complete']
print('Uttakstid:', nvdb_manifest['retrieved_utc'])
print('API-sider:', len(nvdb_manifest['pages']))
first_page = nvdb_manifest['pages'][0]
payload = (nvdb_raw / first_page['file']).read_bytes()
assert hashlib.sha256(payload).hexdigest() == first_page['sha256']
raw_segment = json.loads(payload)['objekter'][0]
display({k: raw_segment.get(k) for k in ['fylke','kommune','topologinivå','typeVeg','lengde','vegsystemreferanse']})
''')
md('''## 2. Frå råsegment til tabell

`build` flatar ut alle råsvara og kontrollerer hashane. Me held berre
køyrande trafikantgruppe (`K`) på topologinivå `Vegtrase`, med strekning.
Kryss og sideanlegg blir haldne utanfor tabellane, men finst i rådata.

Tre nivå har kvar sin nøkkel:

| Nivå | Nøkkel | Innhald |
|---|---|---|
| Segment | `segment_id` | Geometri, vegreferanse, meterintervall og kommune |
| Delstrekning | `delstrekning_id` | Segment samla innan same delstrekning |
| Strekning | `strekning_id` | Segment samla innan same administrative strekning |

Til dømes tyder `46_FV5623_S1`: fylke 46, fylkesveg, eksisterande fase V,
nummer 5623, strekning 1. Vegnummer åleine er ikkje ein unik nøkkel.
''')
code('''road_export = EXPORT / 'vegnett'
road_export.mkdir(exist_ok=True)
build(nvdb_raw, road_export)  # Byggjer faktisk frå rådata, i notebooken si eksportmappe
segments = pd.read_csv(road_export / 'vegsegment.csv')
subsections = pd.read_csv(road_export / 'delstrekningar.csv')
roads = pd.read_csv(road_export / 'strekningar.csv')
assert segments.segment_id.is_unique and roads.strekning_id.is_unique
assert segments.strekning_id.isin(roads.strekning_id).all()
display(segments[['segment_id','strekning_id','delstrekning','fra_meter','til_meter','lengde_m','arm','type_veg']].head())
display(roads.head())
''')
md('''## 3. Sjå sjølv korleis aggregeringa fungerer

Her byggjer me dei viktigaste strekningsfelta direkte med Pandas `groupby`.
Me kontrollerer resultatet mot tabellen frå produksjonsskriptet.

Strekningane er administrative NVDB-einingar, **ikkje faste 10 km-intervall**.
Summert segmentlengd kan omfatte armar og parallelle løp. Hovudløpslengd
utelèt armar, men er heller ikkje nødvendigvis éin samanhengande trasé.
Ferje kan vere med; sjå `type_veg` om du vil avgrense vegutvalet seinare.
''')
code('''grouped = segments.groupby('strekning_id').agg(
    segment_antal=('segment_id','size'),
    lengde_m=('lengde_m','sum'),
    delstrekningar_antal=('delstrekning','nunique'),
    kommunar_antal=('kommune','nunique')).reset_index()
check = roads[['strekning_id','segment_antal','lengde_m']].merge(grouped, on='strekning_id', validate='one_to_one', suffixes=('_fil','_groupby'))
assert check.segment_antal_fil.eq(check.segment_antal_groupby).all()
assert np.allclose(check.lengde_m_fil, check.lengde_m_groupby, atol=0.001)
print(f'{len(segments):,} segment → {len(subsections):,} delstrekningar → {len(roads):,} strekningar')
display(segments.type_veg.value_counts().rename('segment_antal'))
fig, axes = plt.subplots(1,2,figsize=(11,3.8))
axes[0].hist(roads.lengde_m/1000,bins=40,color='#267c9b')
axes[0].set(xlabel='Summert strekningslengd (km)',ylabel='Strekningar',title='Lengdene varierer')
roads.vegkategori.value_counts().reindex(['E','R','F']).plot.bar(ax=axes[1],color=['#496a81','#789f71','#be8d49'],rot=0)
axes[1].set(xlabel='Vegkategori',ylabel='Strekningar',title='E: europa, R: riks, F: fylkesveg')
fig.tight_layout(); plt.show()
''')
md('''## 3b. Lagre vegnettet i SQLite

SQLite samlar tabellane i éi databasefil, og Python har `sqlite3` innebygd.
Me lagrar dei same felta som i CSV, med primærnøklar som hindrar duplikat
og framandnøklar som sikrar at segment viser til rett delstrekning og strekning.
`PRAGMA foreign_keys = ON` aktiverer kontrollen på denne tilkoplinga.

Databasen heiter `data/notebook/vegnett_vegmeldingar/vegnett.sqlite`.
Dette er ei læringskopi av eitt vegnettsuttak. Ved ny køyring erstattar cella
dei tre vegtabellane og uttaksmetadataa i éin transaksjon; feil rullar
endringane tilbake. Rådata og CSV er framleis tilgjengelege.

Geometrien er WKT-tekst med SRID. Vanleg SQLite utfører ikkje geografiske
operasjonar på teksten; me bruker Shapely og PyProj til geometribehandling.
Fila blir lukka når cella er ferdig. Ved aktiv bruk på fleire maskiner bør
databasen liggje utanfor OneDrive, med sikkerheitskopiar når han er lukka.
''')
code('''import sqlite3
DB_PATH = EXPORT / 'vegnett.sqlite'

def sql_name(name):
    # Siter feltnamn frå våre eigne tabellar som SQL-identifikatorar.
    return '"' + name.replace('"','""') + '"'

def create_and_insert(connection, table_name, frame, primary_key, constraints=()):
    definitions = []
    for column, dtype in frame.dtypes.items():
        if pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_bool_dtype(dtype):
            sql_type = 'INTEGER'
        elif pd.api.types.is_float_dtype(dtype):
            sql_type = 'REAL'
        else:
            sql_type = 'TEXT'
        required = ' NOT NULL' if column in {primary_key,'strekning_id','delstrekning_id'} else ''
        definitions.append(f'{sql_name(column)} {sql_type}{required}')
    definitions.append(f'PRIMARY KEY ({sql_name(primary_key)})')
    definitions.extend(constraints)
    connection.execute(f'CREATE TABLE {sql_name(table_name)} (' + ', '.join(definitions) + ')')
    # Parameterbinding skil dataverdiar frå SQL-koden. Manglande verdi blir NULL.
    placeholders = ', '.join('?' for _ in frame.columns)
    values = (tuple(None if pd.isna(value) else value for value in row)
              for row in frame.itertuples(index=False,name=None))
    connection.executemany(f'INSERT INTO {sql_name(table_name)} VALUES ({placeholders})',values)

connection = sqlite3.connect(DB_PATH)
try:
    connection.execute('PRAGMA foreign_keys = ON')
    with connection:
        connection.execute('BEGIN')
        # Fjern barn før foreldre; berre notebooken sine vegtabellar blir erstatta.
        for table in ['vegsegment','delstrekningar','strekningar','vegnett_uttak']:
            connection.execute(f'DROP TABLE IF EXISTS {sql_name(table)}')
        create_and_insert(connection,'strekningar',roads,'strekning_id')
        create_and_insert(connection,'delstrekningar',subsections,'delstrekning_id',[
            'FOREIGN KEY (strekning_id) REFERENCES strekningar(strekning_id)',
            'UNIQUE (delstrekning_id, strekning_id)'])
        create_and_insert(connection,'vegsegment',segments,'segment_id',[
            'FOREIGN KEY (strekning_id) REFERENCES strekningar(strekning_id)',
            'FOREIGN KEY (delstrekning_id, strekning_id) REFERENCES delstrekningar(delstrekning_id, strekning_id)'])
        connection.execute('CREATE INDEX idx_vegsegment_strekning ON vegsegment(strekning_id)')
        connection.execute('CREATE INDEX idx_vegsegment_delstrekning ON vegsegment(delstrekning_id)')
        connection.execute('CREATE INDEX idx_vegnummer ON strekningar(vegkategori, vegnummer)')
        connection.execute('CREATE TABLE vegnett_uttak (id INTEGER PRIMARY KEY CHECK (id=1), manifest_json TEXT NOT NULL)')
        connection.execute('INSERT INTO vegnett_uttak VALUES (?, ?)',(1,json.dumps(nvdb_manifest,ensure_ascii=False)))
    assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    for name, expected in [('strekningar',len(roads)),('delstrekningar',len(subsections)),('vegsegment',len(segments))]:
        count = connection.execute(f'SELECT COUNT(*) FROM {sql_name(name)}').fetchone()[0]
        assert count == expected
        print(name, ':', count, 'rader')
    # Kontroller at databasen faktisk avviser ein ugyldig vegkopling.
    connection.execute('SAVEPOINT fk_test')
    try:
        connection.execute('UPDATE vegsegment SET strekning_id=? WHERE segment_id=?',
                           ('__ukjend_strekning__',str(segments.iloc[0].segment_id)))
    except sqlite3.IntegrityError:
        print('Framandnøkkelkontroll: ugyldig kopling vart avvist')
    else:
        raise AssertionError('Ugyldig vegkopling vart ikkje avvist')
    finally:
        connection.execute('ROLLBACK TO fk_test')
        connection.execute('RELEASE fk_test')
    query = """SELECT s.strekning_id, s.vegnummer, s.strekning,
                      ROUND(s.lengde_m/1000.0, 3) AS lengde_km,
                      COUNT(v.segment_id) AS segment_antal
               FROM strekningar AS s
               LEFT JOIN vegsegment AS v ON v.strekning_id = s.strekning_id
               WHERE s.vegkategori = ? AND s.vegnummer = ?
               GROUP BY s.strekning_id ORDER BY s.strekning"""
    display(pd.read_sql_query(query,connection,params=('F',5623)))
finally:
    connection.close()
print('Lagra og lukka:',DB_PATH)
''')
md('''## 4. Vis vegnettet som kart med Matplotlib

WKT er tekstrepresentasjonen av linjegeometrien. SRID 5973 er eit
tredimensjonalt koordinatsystem; me bruker den horisontale delen og
transformerer til EPSG:25833, med meter som eining. Me droppar høgda i kartet.

Me samlar segmentlinjer per strekning og brukar lik målestokk på aksane.
Det same linjegrunnlaget blir brukt i den geografiske vegmeldingskoplinga.
''')
code('''assert set(segments.srid) == {5973}
project = Transformer.from_crs(CRS.from_epsg(5973).sub_crs_list[0],25833,always_xy=True)
to_utm = Transformer.from_crs(4326,25833,always_xy=True)
roads = roads.sort_values('strekning_id').reset_index(drop=True)
section_lines = []
for sid, group in segments.groupby('strekning_id',sort=True):
    line = shapely.union_all(shapely.force_2d(shapely.from_wkt(group.geometri_wkt.to_numpy())))
    section_lines.append(transform(project.transform,line))
assert len(section_lines) == len(roads)
tree = shapely.STRtree(section_lines)

def line_parts(geometry):
    if geometry.geom_type == 'LineString':
        return [np.asarray(geometry.coords)]
    return [part for g in geometry.geoms for part in line_parts(g)]

def draw_network(ax, indices=None, color='#8c9ba5', linewidth=0.4):
    indices = range(len(section_lines)) if indices is None else indices
    parts = [part for i in indices for part in line_parts(section_lines[i])]
    ax.add_collection(LineCollection(parts,colors=color,linewidths=linewidth))
    ax.autoscale(); ax.set_aspect('equal')
    ax.set(xlabel='Aust (meter, EPSG:25833)',ylabel='Nord (meter)')

fig, ax = plt.subplots(figsize=(8,9))
for category,color in [('F','#9bb0b8'),('R','#d08041'),('E','#264e70')]:
    draw_network(ax,roads.index[roads.vegkategori.eq(category)],color,0.55)
    ax.plot([],[],color=color,label=category)
ax.legend(title='Vegkategori'); ax.set_title('Vegnettsuttaket i Vestland')
fig.tight_layout(); fig.savefig(EXPORT/'vegnett_vestland.png',dpi=150); plt.show()
''')
md('''## 5. Hente historiske vegmeldingar frå Xgeo

NVE sitt Xgeo-lag inneheld vegmeldingar frå Statens vegvesen. Me hentar
nasjonalt og avgrensar geografisk lokalt, slik at gamle fylkesnamn ikkje
blir eit førehandsfilter. Uttaket er årsvis, med opptil 1 000 postar per side,
stabil sortering, og teljing før og etter nedlastinga.

Me prøvde perioden 2006–2026, men dette laget har ingen postar i 2006–2009.
Den tidlegaste posten er frå 2010. Tomme år er ikkje dokumentasjon på null skred.
Dette er dei tilgjengelege meldingane i dette laget, ikkje ein garanti for
at alle historiske trafikkmeldingar er arkiverte.
''')
code('''from hent_xgeo_vegmeldingar import URL, ORDER, END
xgeo_raw = ROOT / 'data/raw/xgeo_vegmeldingar'
example_query = dict(f='json',where="FROM_DATE >= timestamp '2018-01-01 00:00:00' AND FROM_DATE < timestamp '2019-01-01 00:00:00'",
                     outFields='*',returnGeometry='true',outSR=4326,orderByFields=ORDER,resultOffset=0,resultRecordCount=1000)
print(URL + '?' + urlencode(example_query))
if FETCH_XGEO:
    run_script('hent_xgeo_vegmeldingar.py')
xgeo_manifest = read_json(xgeo_raw/'manifest.json')
assert xgeo_manifest['complete']
year_counts = pd.DataFrame([{'år':y['year'],'postar':y['rows']} for y in xgeo_manifest['years']])
verified_rows = 0
example_features = None
for year in xgeo_manifest['years']:
    count = 0
    for page in year['pages']:
        payload = (xgeo_raw/page['file']).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == page['sha256']
        data = json.loads(gzip.decompress(payload))
        assert len(data['features']) == page['rows']
        count += len(data['features'])
        if example_features is None and year['year'] == YEAR:
            example_features = data['features']
    assert count == year['rows'] == year['count_before'] == year['count_after']
    verified_rows += count
assert verified_rows == xgeo_manifest['rows']
print('Kontrollerte råpostar:', verified_rows)
fig, ax = plt.subplots(figsize=(11,3.5))
ax.bar(year_counts['år'],year_counts.postar,color='#267c9b')
ax.set(xlabel='År',ylabel='Nasjonale meldingspostar',title='Tilgjengeleg Xgeo-arkiv – ikkje tal på skred')
fig.tight_layout(); plt.show()
raw_messages = pd.DataFrame([f['attributes'] for f in example_features])
display(raw_messages[['NAME','ROAD_TYPE','ROAD_NUMBER','MSG_DESCRIPTION','FREE_TEXT']].head())
''')
md('''## 6. Frå råmelding til geografisk kandidat

Produksjonsløpet bevarer identifikatorar, tekst, tidsfelt og koordinat.
`SHOW_X/SHOW_Y` gir visingspunkt; rågeometrien blir brukt som reserve.
Punktet blir transformert frå lengde-/breiddegrad til EPSG:25833.

Ein studie-kandidat ligg innan 1 km frå vegnettet **eller** har eit relevant
fylkesnamn i teksten. Dette er ei brei avgrensing, ikkje det endelege positive
utfallet. Den endelege vegkoplinga krev høgst 100 meter og eintydig plassering.

Dei ferdige kandidatane omfattar alle klassar, slik at me kan undersøkje
både behaldne og forkasta meldingar. `REBUILD_MESSAGE_LINKS=True` køyrer
heile produksjonsfilteret og oppdaterer produksjonstabellane; standarden
les siste kontrollerte resultat. Historiske nummerlister må vere henta først.
''')
code('''if REBUILD_MESSAGE_LINKS:
    run_script('filtrer_xgeo_vegmeldingar.py')
    run_script('valider_historisk_kopling.py')
    run_script('valider_vegmeldingar.py')
message_root = ROOT/'data/processed/vegmeldingar'
messages = pd.read_parquet(message_root/'meldingar_vestland_kandidatar.parquet')
filter_report = read_json(message_root/'filterrapport.json')
assert messages.row_id.is_unique
print('Nasjonale råpostar:', filter_report['national_rows'])
print('Geografiske/namnebaserte kandidatar:', len(messages))
display(messages[['row_id','dato','ROAD_TYPE','ROAD_NUMBER','NAME','anchor_x_25833','anchor_y_25833']].head())
''')
md('''## 7. Tekstfilter: faktisk meldt skred eller berre fare?

Me klassifiserer ut frå både meldingstekst og fritekst. «Fare for ras» er
ikkje eit positivt skred. Kontrollert utløsning, usikre prognosar og opning
etter skred blir haldne utanfor positive førstegongsmeldingar.

`classify` er den same funksjonen som produksjonsløpet brukar. Regelen
leitar etter uttrykk for skred/nedfall, men unngår reine fareuttrykk.
Alle skredtypar er samla. Isnedfall er med i det breie utfallet.
Reglane kan ta feil; døma og kontrollutvalet gjer dei etterprøvbare.
''')
code('''from filtrer_xgeo_vegmeldingar import classify, parse_time
examples = ['Stengt på grunn av snøras.', 'Stengt på grunn av fare for ras.',
            'Fare for steinskred/steinsprang, vegen er stengt.',
            'Stengt på grunn av snøras og fare for ras.',
            'Åpen for trafikk etter snøras.', 'Kontrollert utløsning av snøskred.',
            'Mulig jordskred, vegen er stengt.', 'Isnedfall, ett stengt kjørefelt.']
display(pd.DataFrame([{'tekst':s,'klasse':classify(s)[0],'regel':classify(s)[1]} for s in examples]))
# Utfør faktisk tekstbehandling av kandidatane i notebooken:
reclassified = messages.text.map(lambda text:classify(text)[0])
assert reclassified.eq(messages.klasse).all()
class_counts = reclassified.value_counts()
fig, ax = plt.subplots(figsize=(10,3.8))
class_counts.sort_values().plot.barh(ax=ax,color='#267c9b')
ax.set(xlabel='Meldingsrader',ylabel='',title='Klassane etter tekstfilteret')
fig.tight_layout(); plt.show()
display(messages.loc[messages.klasse.eq('meldt_skred'),['dato','NAME','text','regel']].sample(6,random_state=SEED))
''')
md('''## 8. Historiske vegnummer og geografisk kopling

Me bruker dei offisielle reformlistene for Hordaland og Sogn og Fjordane.
Eit gammalt nummer kan bli fleire nye: Fv152 vart mellom anna Fv5606 og
Fv5617. Gammalt fylke og geografisk plassering er derfor nødvendige.

Tillatne kandidatar har same vegkategori og anten dagens nummer eller eit
nummerpar i reformlista for riktig gammalt fylke. Punktet må vere innan
100 meter, med minst 20 meter avstandsmargin til neste tillatne strekning.
Start-/endepunkt meir enn 100 meter frå den valde strekninga gir grov
stadfesting og utelating frå det strenge utvalet.

Xgeo manglar hovudparsell og meterverdi. Me bruker derfor koordinat til å
skilje greinene, ikkje fullstendige historiske vegreferanseoppslag.
Gamle alias er tillatne gjennom 2021 som ei dokumentert overgangsregel.
NVDB-endringsdatoen i lista er ikkje nødvendigvis referansens gyldigheitsdato;
bruk etter denne datoen blir markert. Andre omnummereringar, kategoriendringar
og flytta vegar kan framleis mangle kopling.
''')
code('''from historiske_vegnummer import load_crosswalk, alias_records, old_county, select_evidence
crosswalk = load_crosswalk()
aliases = alias_records(crosswalk)
display(crosswalk.loc[crosswalk.old_county.eq(14) & crosswalk.old_number.isin([152,241,337]),
    ['old_county','vegkategori','old_number','old_hp','new_number','nvdb_changed_date','description']])
# Følg éi verkeleg melding gjennom den geografiske nummeromsetjinga:
example = messages.loc[messages.historisk_omnummerering & messages.strict_row & messages.vegnummer.eq(241)].iloc[0]
point = shapely.Point(example.anchor_x_25833,example.anchor_y_25833)
candidate_indices = tree.query(point,predicate='dwithin',distance=100)
candidate_rows = []
for j in candidate_indices:
    road = roads.iloc[j]
    county_set = {old_county(int(k)) for k in str(road.kommunar).split('|')}
    # Denne enkle demonstrasjonen krev at strekninga har eitt gammalt fylke.
    # Produksjonskoden handterer også strekningar som kryssar gammal fylkesgrense.
    county = next(iter(county_set)) if len(county_set)==1 else None
    evidence = select_evidence(aliases,county,example.vegkategori,example.vegnummer,road.vegnummer,example.dato)
    allowed = road.vegkategori == example.vegkategori and (road.vegnummer==example.vegnummer or bool(evidence))
    candidate_rows.append(dict(strekning_id=road.strekning_id,dagens_nummer=road.vegnummer,
        gammalt_fylke=county,avstand_m=point.distance(section_lines[j]),tillaten=allowed))
candidate_table = pd.DataFrame(candidate_rows).sort_values('avstand_m')
display(example[['dato','NAME','ROAD_NUMBER','kopla_vegnummer','strekning_id','avstand_m','koplingsregel']].to_frame('verdi'))
display(candidate_table)
selected = candidate_table.loc[candidate_table.tillaten].iloc[0]
assert selected.strekning_id == example.strekning_id
''')
md('''## 9. Sjå koplinga på kart og undersøk tap i filteret

På detaljkartet viser den farga linja den valde strekninga, og punktet
meldinga sitt visingspunkt. Punktet er ikkje nødvendigvis den eksakte skredstaden.

Filtertabellen under bruker **meldingsrader**. Seinare samlar me fleire
oppdateringar til episodar; difor er meldingsrader, episodar og positive
strekning–døgn ulike tal.
''')
code('''selected_index = roads.index[roads.strekning_id.eq(example.strekning_id)][0]
fig, ax = plt.subplots(figsize=(8,5))
draw_network(ax,color='#bac5cb',linewidth=0.7)
draw_network(ax,[selected_index],color='#d07234',linewidth=2.5)
ax.scatter([point.x],[point.y],s=65,color='#9c2638',zorder=5,label='Meldingspunkt')
ax.set_xlim(point.x-4000,point.x+4000); ax.set_ylim(point.y-2500,point.y+2500)
ax.legend(); ax.set_title(f'Gammal Fv241 → Fv5623: {example.strekning_id}')
fig.tight_layout(); fig.savefig(EXPORT/'historisk_kopling_detalj.png',dpi=150); plt.show()

period = messages.dato.between('2013-01-01','2026-10-03')
actual = messages.klasse.eq('meldt_skred')
steps = pd.DataFrame({'steg':['Studiekandidatar i analyseperioden','Tekst omtalar meldt skred',
    'Har eintydig vegkopling','Har også presis nok utstrekning og UTC-dato'],
    'meldingsrader':[int(period.sum()),int((period & actual).sum()),
        int((period & actual & messages.strekning_id.notna()).sum()),int(messages.strict_row.sum())]})
display(steps)
display(pd.read_csv(message_root/'historisk_kopling_per_ar.csv'))
''')
md('''## 10. Tid: frå UTC til norsk kalenderdato

Kjelda bruker både millisekund og ISO-strengar. UTC-feltet blir prioritert,
og datoen blir avleidd i `Europe/Oslo`. Ved midnatt kan norsk kalenderdato
vere ulik UTC-datoen. Manglande UTC-tid gir ikkje positive strenge etikettar.

Etikettdatoen er meldingas gyldig-frå-dato. Me kjenner ikkje nødvendigvis
tidspunktet då skredet faktisk gjekk.
''')
code('''times = messages.FROM_DATE_UTC.map(parse_time)
local_dates = times.dt.tz_convert('Europe/Oslo').dt.tz_localize(None).dt.normalize()
assert local_dates.equals(messages.dato)
time_example = pd.Timestamp('2018-01-01 23:30:00',tz='UTC')
print('UTC:',time_example,'→ norsk tid:',time_example.tz_convert('Europe/Oslo'))
display(messages[['FROM_DATE_UTC','from_utc','dato','date_utc_missing']].head())
''')
md('''## 11. Bygg episodekandidatar sjølv

Me grupperer etter kjelda sin situasjons-ID og kopla strekning. Eit opphald
på meir enn sju døgn mellom positive meldingar startar ein ny episode.
Denne heuristikken kan både slå saman ulike skred og dele ei lang hending.

Me bruker første positive melding til dato og kontroll av strengt utval.
Ei grov første melding blir ikkje flytta til datoen for ei reinare oppdatering.
Her utfører notebooken grupperinga og kontrollerer henne mot produksjonsresultatet.
''')
code('''positive_messages = messages.loc[messages.klasse.eq('meldt_skred') & messages.strekning_id.notna() & messages.from_utc.notna()].copy()
positive_messages = positive_messages.sort_values(['situation_key','strekning_id','from_utc','row_id'])
gap = positive_messages.groupby(['situation_key','strekning_id']).from_utc.diff()
positive_messages['episode_number'] = gap.gt(pd.Timedelta(days=7)).groupby(
    [positive_messages.situation_key,positive_messages.strekning_id]).cumsum().astype(int)
episode_keys = ['situation_key','strekning_id','episode_number']
first_messages = positive_messages.groupby(episode_keys,sort=False).head(1).copy()
episode_sizes = positive_messages.groupby(episode_keys).size().rename('message_rows').reset_index()
episodes = first_messages[['situation_key','strekning_id','episode_number','row_id','dato','strict_row','text']].merge(
    episode_sizes,on=episode_keys,validate='one_to_one')
episodes = episodes.rename(columns={'row_id':'first_row_id','strict_row':'strict_candidate','text':'first_text'})
production_episodes = pd.read_parquet(message_root/'skredepisodar_kandidatar.parquet')
assert len(episodes)==len(production_episodes)
assert set(episodes.first_row_id)==set(production_episodes.first_row_id)
strict_episodes = episodes.loc[episodes.strict_candidate].copy()
assert len(strict_episodes)==int(production_episodes.strict_candidate.sum())
print('Strenge meldingsrader:',int(messages.strict_row.sum()))
print('Strenge episodekandidatar:',len(strict_episodes))
display(strict_episodes[['strekning_id','dato','message_rows','first_text']].head())
''')
md('''## 12. Lag positive strekning–døgn

Eit **positivt strekning–døgn** er éi strekning på éin dato med minst éin
behalden skredepisode. Tre episodar same dag på same strekning gir eitt
positivt døgn. Same dato på to strekningar gir to. Ei fem dagar lang
stenging gir ikkje automatisk fem positive døgn.

Denne tabellen inneheld berre positive kombinasjonar. Ho gir eit eige
episodetal og ein binær indikator; talet på meldingar er ikkje skredtalet.
''')
code('''daily = strict_episodes.groupby(['strekning_id','dato']).size().rename('melde_skred_episodar').reset_index()
daily['vegmelding_skred'] = 1
production_daily = pd.read_parquet(message_root/'vegmelding_skred_dogn.parquet')
pd.testing.assert_frame_equal(daily.sort_values(['strekning_id','dato']).reset_index(drop=True),
    production_daily[daily.columns].sort_values(['strekning_id','dato']).reset_index(drop=True),check_dtype=False)
assert not daily.duplicated(['strekning_id','dato']).any()
print('Positive strekning–døgn:',len(daily))
display(daily.head())
annual_days = daily.groupby(daily.dato.dt.year).size()
fig, ax = plt.subplots(figsize=(10,3.5))
ax.bar(annual_days.index,annual_days.values,color='#d07234')
ax.set(xlabel='År',ylabel='Positive strekning–døgn',title='Behaldne vegmeldingar etter nummerretting')
fig.tight_layout(); plt.show()
''')
md('''## 13. Populer strekningsdatasettet med vegmeldingar

Ein venstre-kopling (`left merge`) bevarer alle 957 strekningane. Me legg
til episodetal, positive døgn og første/siste positive meldingsdato.
Strekningar utan behaldne episodar får null i teljefelta og tom dato.

Dette er ei **beskrivande oversikt over heile perioden**. Totalane må ikkje
brukast som historiske ML-prediktorar utan tidsavgrensing; då ville framtidige
hendingar lekke inn. Null betyr ingen behalden melding, ikkje dokumentert fråvær av skred.
''')
code('''episode_summary = strict_episodes.groupby('strekning_id').agg(
    skredepisodar=('first_row_id','size'),
    meldingar_i_behaldne_episodar=('message_rows','sum'),
    forste_positive_dato=('dato','min'),siste_positive_dato=('dato','max')).reset_index()
day_summary = daily.groupby('strekning_id').size().rename('positive_dogn').reset_index()
enriched = roads.merge(episode_summary,on='strekning_id',how='left',validate='one_to_one').merge(
    day_summary,on='strekning_id',how='left',validate='one_to_one')
for column in ['skredepisodar','meldingar_i_behaldne_episodar','positive_dogn']:
    enriched[column] = enriched[column].fillna(0).astype('int64')
enriched['analyse_fra'] = '2013-01-01'
enriched['analyse_til'] = '2026-10-03'
assert len(enriched)==len(roads)
assert enriched.positive_dogn.sum()==len(daily)
assert enriched.skredepisodar.sum()==len(strict_episodes)
display(enriched[['strekning_id','vegkategori','vegnummer','strekning','lengde_m','skredepisodar','positive_dogn','forste_positive_dato','siste_positive_dato']].sort_values('positive_dogn',ascending=False).head(12))
''')
md('''## 14. Kart over berikinga

Kartet viser positive døgn per strekning gjennom heile analyseperioden.
Det viser registrerte meldingar og koplingsresultat, ikkje berekna skredfare.
Lange vegar og ulik registreringspraksis påverkar tala. Grått betyr ingen
behalden episode; me kan ikkje tolke det som at vegen er trygg.
''')
code('''from matplotlib.colors import Normalize
fig, ax = plt.subplots(figsize=(8,9))
draw_network(ax,color='#c8cfd3',linewidth=0.5)
parts, values = [], []
for i,row in enriched.iterrows():
    if row.positive_dogn > 0:
        for part in line_parts(section_lines[i]):
            parts.append(part); values.append(row.positive_dogn)
collection = LineCollection(parts,cmap='YlOrRd',norm=Normalize(1,max(values)),linewidths=1.25)
collection.set_array(np.asarray(values)); ax.add_collection(collection)
fig.colorbar(collection,ax=ax,label='Positive strekning–døgn, 2013–2026',shrink=0.65)
ax.set_title('Vegmeldingar kopla til administrative strekningar')
fig.tight_layout(); fig.savefig(EXPORT/'vegmeldingar_strekningskart.png',dpi=150); plt.show()
''')
md('''## 15. Lag ei komplett strekning–døgnstabell for eitt år

For seinare døgnbasert analyse treng me også kombinasjonane utan behaldne
episodar. Me lagar alle strekningar × datoar for `YEAR`, og koplar positive
døgn inn. Resultatet har éi rad per strekning/dato, og kan seinare koplast
til vêrdata på same nøkkel.

Me bruker 2013 og seinare for denne analyseperioden. Ikkje fyll år utan
kjeldedekning med null og tolk dei som observerte skredfrie døgn.
''')
code('''assert 2013 <= YEAR <= 2026
year_end = min(pd.Timestamp(f'{YEAR}-12-31'),pd.Timestamp('2026-10-03'))
dates = pd.date_range(f'{YEAR}-01-01',year_end,freq='D')
panel = pd.MultiIndex.from_product([roads.strekning_id,dates],names=['strekning_id','dato']).to_frame(index=False)
panel = panel.merge(daily.loc[daily.dato.dt.year.eq(YEAR)],on=['strekning_id','dato'],how='left',validate='one_to_one')
panel['melde_skred_episodar'] = panel.melde_skred_episodar.fillna(0).astype('int16')
panel['vegmelding_skred'] = panel.vegmelding_skred.fillna(0).astype('int8')
# Ta berre statiske vegfelt frå vegtabellen, ikkje totalar frå framtidige episodar:
panel = panel.merge(roads[['strekning_id','vegkategori','vegnummer','strekning','lengde_m']],on='strekning_id',validate='many_to_one')
assert len(panel)==len(roads)*len(dates)
assert not panel.duplicated(['strekning_id','dato']).any()
assert panel.vegmelding_skred.sum()==len(daily.loc[daily.dato.dt.year.eq(YEAR)])
assert panel.vegmelding_skred.eq(panel.melde_skred_episodar.gt(0)).all()
print(f'{YEAR}: {len(panel):,} strekning–døgn, {int(panel.vegmelding_skred.sum())} positive')
display(panel.loc[panel.vegmelding_skred.eq(1)].head())
''')
md('''## 16. Eksporter og kontroller resultatet

Notebooken skriv eigne filer under `data/notebook/vegnett_vegmeldingar/`.
Produksjonsdataa og før-snapshotet blir ikkje overskrivne i standardkøyringa.
CSV er UTF-8 med BOM. Parquet bevarer datatypar og er praktisk for vidare
datakopling. Kart er eksporterte som PNG.
''')
code('''enriched.to_csv(EXPORT/'strekningar_med_vegmeldingar.csv',index=False,encoding='utf-8-sig')
enriched.to_parquet(EXPORT/'strekningar_med_vegmeldingar.parquet',index=False)
strict_episodes.to_parquet(EXPORT/'skredepisodar_strekning.parquet',index=False)
daily.to_parquet(EXPORT/'positive_strekning_dogn.parquet',index=False)
panel.to_parquet(EXPORT/f'strekning_dogn_{YEAR}.parquet',index=False)
csv_roundtrip = pd.read_csv(EXPORT/'strekningar_med_vegmeldingar.csv')
assert csv_roundtrip.strekning_id.is_unique and len(csv_roundtrip)==len(roads)
assert csv_roundtrip.positive_dogn.sum()==len(daily)
pd.testing.assert_frame_equal(pd.read_parquet(EXPORT/f'strekning_dogn_{YEAR}.parquet'),panel)
validation = dict(road_sections=len(roads),segments=len(segments),raw_xgeo_rows=verified_rows,
    study_message_rows=len(messages),strict_episodes=len(strict_episodes),positive_section_days=len(daily),
    populated_sections=int(enriched.positive_dogn.gt(0).sum()),panel_year=YEAR,panel_rows=len(panel),
    checks_passed=True,qualification='Tekniske kontrollar; meldingstekst og faktisk skredstad er ikkje manuelt verifiserte')
(EXPORT/'notebook_kontroll.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
display(validation)
display(pd.DataFrame([{'fil':p.name,'MB':round(p.stat().st_size/1e6,2)} for p in sorted(EXPORT.iterdir()) if p.is_file()]))
''')
md('''## 17. Manuell kontroll og vidare læring

1. Vel ein annan historisk veg i kapittel 8. Kva skjer når det gamle nummeret har fleire nye greinnummer?
2. Undersøk ti `skredfare`-meldingar. Finst faktisk skred omtalt i nokre av dei?
3. Finn `meldt_skred` utan kopla strekning. Er årsaka nummer, koordinat, vegkategori eller tvitydig plassering?
4. Samanlikn ei kort og ei lang strekning. Kvifor er rå episodetal utilstrekkelege som fareindikator?
5. Byt `YEAR`, og sjå korleis meldingsdekninga endrar seg.

`data/processed/vegmeldingar/manuell_kontroll.csv` inneheld eit stratifisert
utval med tomme kontrollfelt. Fyll dei ut i ei eiga kopi. Kvalitetskontroll
av tekst og stadfesting er nødvendig før me tolkar etikettane som faktiske skred.

Vidare arbeid med vêr og modellering finst i `skred_ml_laering.ipynb`.

Kjelder og detaljar:

- [NVDB API Les V4](https://nvdb-docs.atlas.vegvesen.no/nvdbapil/v4/Vegnett/)
- [NVE Xgeo-laget](https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer/13)
- [Vegvesenet: nye vegnummer](https://www.vegvesen.no/kjoretoy/yrkestransport/veglister-og-dispensasjoner/nye-vegnummer/)
- [Historisk kopling i prosjektet](../HISTORISK_VEGKOPLING.md)
- [Tekstfilter, episodar og avgrensingar](../VEGMELDINGAR_UTTAK.md)
''')

notebook = dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python (aktsomhet)',language='python',name='python3'),
    language_info=dict(name='python',version='3.12')),nbformat=4,nbformat_minor=5)
for index, cell in enumerate(cells):
    cell['id'] = f'dataarbeid-{index:03d}'
path = ROOT/'notebooks/vegnett_vegmeldingar_dataarbeid.ipynb'
path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding='utf-8')
print(path)
