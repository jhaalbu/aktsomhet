"""Make a small, self-contained beginner notebook; no production helpers."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cells = []
def md(s):
    cells.append(dict(cell_type='markdown',metadata={},source=s.strip().splitlines(keepends=True)))
def code(s):
    cells.append(dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=s.strip().splitlines(keepends=True)))

md('''# Rv13: eit enkelt døme på dataarbeid

Her lærer me eitt steg om gongen, med berre **Rv13 i Vestland**:

1. Hente vegsegment frå NVDB.
2. Samle segment til strekningar og teikne dei på kart.
3. Hente vegmeldingar frå Xgeo og finne dei som ligg nær denne vegen.
4. Lage ein 2 km-buffer rundt kvar strekning.
5. Finne 1 km-gridcellene som overlappar bufferane.

Det er inga modelltrening, database eller avansert produksjonskode her.
All databehandling står i cellene. Me bruker Pandas til tabellar,
Shapely til linjer og flater, PyProj til koordinat og Matplotlib til kart.

Vel prosjektet si `.venv` som Python-kjerne. Køyr cellene ovanfrå og ned.
Første køyring hentar data frå internett. Seinare køyringar bruker dei lokale
JSON-filene. Alle filer for dømet ligg i `data/notebook/rv13_enkelt/`.
''')
code('''from pathlib import Path
import json
import math
import requests
import pandas as pd
import matplotlib.pyplot as plt
from shapely import wkt
from shapely.geometry import Point, box
from shapely.ops import unary_union, transform
from pyproj import CRS, Transformer

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p/'scripts/hent_nvdb.py').exists())
MAPPE = ROOT / 'data/notebook/rv13_enkelt'
MAPPE.mkdir(parents=True,exist_ok=True)

FYLKE = 46                   # Vestland
VEGNUMMER = 13                # Rv13
FRA_AAR = 2024
TIL_AAR = 2025                # Begge desse åra er med
BUFFER_METER = 2000
MELDING_AVSTAND_METER = 1000   # Breitt kandidatfilter, ikkje stadnøyaktigheit
HENT_PAA_NYTT = False
assert 2006 <= FRA_AAR <= TIL_AAR <= 2025
print('Filer:',MAPPE)
''')
md('''## 1. Hent vegdata

NVDB gir mange små **segment**. Ei strekning består av fleire slike segment.
Me ber om eksisterande riksveg 13 i fylke 46. API-et gir data i sider,
så løkka hentar neste side til det ikkje er fleire.

`requests.get` sender førespurnaden. `.json()` gjer svaret om til Python-data.
Me lagrar resultatet slik at me slepp å hente det igjen kvar gong.
''')
code('''vegfil = MAPPE / 'rv13_vegnett.json'
nvdb_url = 'https://nvdbapiles.atlas.vegvesen.no/vegnett/api/v4/veglenkesekvenser/segmentert'
nvdb_filter = {'fylke':FYLKE,'vegsystemreferanse':f'RV{VEGNUMMER}','antall':1000}

if vegfil.exists() and not HENT_PAA_NYTT:
    vegdata = json.loads(vegfil.read_text(encoding='utf-8'))
else:
    alle_segment = []
    parametre = nvdb_filter.copy()
    while True:
        svar = requests.get(nvdb_url,params=parametre,headers={'X-Client':'aktsomhet-rv13-laering'},timeout=60)
        svar.raise_for_status()
        side = svar.json()
        alle_segment.extend(side['objekter'])
        print('Henta segment:',len(alle_segment))
        neste = side.get('metadata',{}).get('neste',{})
        if not neste.get('start'):
            break
        parametre['start'] = neste['start']
    vegdata = {'filter':nvdb_filter,'segment':alle_segment}
    vegfil.write_text(json.dumps(vegdata,ensure_ascii=False),encoding='utf-8')
assert vegdata['filter'] == nvdb_filter
print('Segment i råsvaret:',len(vegdata['segment']))
display(vegdata['segment'][0]['vegsystemreferanse'])
''')
md('''## 2. Lag ein segmenttabell

Råsvaret er nøsta: vegnummer og strekning ligg inne i `vegsystemreferanse`.
Me plukkar ut dei felta me treng og legg dei i ei liste med rader.
`pd.DataFrame` gjer denne lista til ein tabell.

Me beheld køyrande vegtrasear med vanleg strekning, og utelèt kryss og
sideanlegg. Armar og ferje kan framleis vere med. Sjå `vegtype` i tabellen.

Geometrien kjem som WKT-tekst. Me les han som ei linje, droppar høgda og
bruker EPSG:25833, der avstandar er i meter.
''')
code('''rader = []
segment_geometri = []
for segment in vegdata['segment']:
    referanse = segment.get('vegsystemreferanse',{})
    veg = referanse.get('vegsystem',{})
    strekning = referanse.get('strekning',{})
    if not strekning or referanse.get('kryssystem') or referanse.get('sideanlegg'):
        continue
    if strekning.get('trafikantgruppe') != 'K' or segment.get('topologinivå') != 'Vegtrase':
        continue
    if veg.get('vegkategori') != 'R' or veg.get('nummer') != VEGNUMMER or veg.get('fase') != 'V':
        continue
    linje = wkt.loads(segment['geometri']['wkt'])
    linje = transform(lambda x,y,z=None:(x,y),linje)
    kilde_crs = CRS.from_epsg(segment['geometri']['srid'])
    horisontal_crs = kilde_crs.sub_crs_list[0] if kilde_crs.is_compound else kilde_crs
    omregning = Transformer.from_crs(horisontal_crs,25833,always_xy=True)
    linje = transform(omregning.transform,linje)
    rader.append({'strekning':strekning['strekning'],'delstrekning':strekning['delstrekning'],
                  'lengde_m':segment['lengde'],'arm':strekning['arm'],'vegtype':segment['typeVeg'],
                  'geometri_wkt':linje.wkt})
    segment_geometri.append(linje)
segmenter = pd.DataFrame(rader)
assert len(segmenter)>0
display(segmenter.head())
display(segmenter.vegtype.value_counts())
''')
md('''## 3. Samle segment til strekningar

`groupby('strekning')` samlar rader som har same strekningsnummer.
Me summerer segmentlengdene og samlar linjene til éin geometri per strekning.

Me bruker **NVDB sine eksisterande strekningar**. Me lagar ikkje nye 10 km-bitar.
Lengdene varierer, og summen kan inkludere armar og parallelle løp.
Tabellen og lista med geometri har same rekkjefølgje.
''')
code('''strekninger = segmenter.groupby('strekning').agg(
    segment_antal=('strekning','size'),lengde_m=('lengde_m','sum')).reset_index()
strekninger['strekning_id'] = strekninger.strekning.map(lambda s:f'{FYLKE}_RV{VEGNUMMER}_S{s}')
strekninger['lengde_km'] = strekninger.lengde_m/1000
linjer = []
for nummer in strekninger.strekning:
    deler = segmenter.loc[segmenter.strekning.eq(nummer),'geometri_wkt']
    linjer.append(unary_union([wkt.loads(tekst) for tekst in deler]))
strekninger['geometri_wkt'] = [linje.wkt for linje in linjer]
hele_vegen = unary_union(linjer)
display(strekninger[['strekning_id','segment_antal','lengde_km']])
print('Strekningar:',len(strekninger))
''')
md('''## 4. Teikn vegen

Nokre strekningar har fleire linjedelar. Den vesle funksjonen under teiknar
både ei enkel linje og ei samling av linjer. Lik målestokk på aksane gjer
at geometrien ikkje blir strekt i kartet.
''')
code('''def tegn_linje(ax,geometri,**stil):
    deler = [geometri] if geometri.geom_type=='LineString' else list(geometri.geoms)
    for del_linje in deler:
        x,y = del_linje.xy
        ax.plot(x,y,**stil)

fig,ax = plt.subplots(figsize=(7,9))
for i,linje in enumerate(linjer):
    tegn_linje(ax,linje,color=plt.cm.tab20(i%20),linewidth=2)
ax.set_aspect('equal')
ax.set(title='Rv13 i Vestland – NVDB-strekningar',xlabel='Aust (meter)',ylabel='Nord (meter)')
fig.tight_layout(); plt.show()
''')
md('''## 5. Hent vegmeldingar frå Xgeo

Me ber om **alle meldingstypar som er arkiverte i Xgeo-laget med vegreferanse Rv13**
for dei valde åra. Me filtrerer ikkje på skred. Me hentar også meldingar frå
andre fylke først; koordinata blir brukte til å finne Vestland-delen etterpå.

Éi melding kan få mange oppdateringar. Rader i dette uttaket er derfor ikkje
det same som uavhengige hendingar. Xgeo-laget er heller ikkje eit fullstendig
arkiv over alle slags historiske trafikkmeldingar.

For enkelheit brukar me berre nummeret Rv13 her. Meldingar med gamle nummer,
til dømes gamle Rv55 på delar av dagens Rv13, er ikkje med. Det større
prosjektdatasettet har meir avansert historisk nummerkopling.
''')
code('''meldingsfil = MAPPE / f'xgeo_rv13_{FRA_AAR}_{TIL_AAR}.json'
xgeo_url = 'https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer/13/query'
where = (f"ROAD_TYPE = 'Rv' AND ROAD_NUMBER = '{VEGNUMMER}' "
         f"AND FROM_DATE >= timestamp '{FRA_AAR}-01-01 00:00:00' "
         f"AND FROM_DATE < timestamp '{TIL_AAR+1}-01-01 00:00:00'")
if meldingsfil.exists() and not HENT_PAA_NYTT:
    meldingsdata = json.loads(meldingsfil.read_text(encoding='utf-8'))
else:
    parametre = {'f':'json','where':where,'outFields':'*','returnGeometry':'true',
                 'outSR':4326,'orderByFields':'FROM_DATE ASC, EXT_REC_NO ASC, VERSION_NO ASC, MSG_NO ASC',
                 'resultOffset':0,'resultRecordCount':1000}
    features = []
    while True:
        svar = requests.get(xgeo_url,params=parametre,timeout=60)
        svar.raise_for_status()
        side = svar.json()
        if 'error' in side:
            raise RuntimeError(side['error'])
        features.extend(side['features'])
        print('Henta meldingsrader:',len(features))
        if not side.get('exceededTransferLimit',False):
            break
        if not side['features']:
            raise RuntimeError('API-et gav ei tom side før pagineringa var ferdig')
        parametre['resultOffset'] += len(side['features'])
    meldingsdata = {'where':where,'features':features}
    meldingsfil.write_text(json.dumps(meldingsdata,ensure_ascii=False),encoding='utf-8')
assert meldingsdata['where']==where
meldinger = pd.DataFrame([f['attributes'] for f in meldingsdata['features']])
assert len(meldinger)>0,'Ingen meldingar i dette utvalet; vel ein annan periode'
display(meldinger[['NAME','ROAD_TYPE','ROAD_NUMBER','MSG_DESCRIPTION','FREE_TEXT']].head())
print('Nasjonale Rv13-meldingsrader:',len(meldinger))
''')
md('''## 6. Finn meldingspunkt nær Rv13 i Vestland

Me bruker visingspunktet (`SHOW_X/SHOW_Y`), eller råpunktet dersom visingspunktet
manglar, og reknar om frå lengde-/breiddegrad til meterkoordinat.

For kvar melding finn me næraste Rv13-strekning. Me beheld meldingar innan
1 km som **kandidatar**, og viser avstanden i tabellen. Det er eit enkelt
læringsfilter: eit visingspunkt kan liggje midt på ei lang stenging og
seier ikkje sikkert kvar hendinga skjedde eller kva strekningar ho råka.
''')
code('''til_meter = Transformer.from_crs(4326,25833,always_xy=True)
koplingar = []
for i,feature in enumerate(meldingsdata['features']):
    attributt = feature['attributes']
    raw_point = feature.get('geometry') or {}
    lon = attributt.get('SHOW_X')
    lat = attributt.get('SHOW_Y')
    if lon is None or lat is None:
        lon,lat = raw_point.get('x'),raw_point.get('y')
    if lon is None or lat is None:
        continue
    x,y = til_meter.transform(float(lon),float(lat))
    punkt = Point(x,y)
    avstander = [punkt.distance(linje) for linje in linjer]
    nermeste = min(range(len(avstander)),key=lambda j:avstander[j])
    if avstander[nermeste] <= MELDING_AVSTAND_METER:
        koplingar.append({'meldingsrad':i,'strekning_id':strekninger.iloc[nermeste].strekning_id,
                         'avstand_m':avstander[nermeste],'x':x,'y':y})
kopling = pd.DataFrame(koplingar)
assert len(kopling)>0,'Ingen punkt nær Rv13 i Vestland i denne perioden'
vegmeldinger = kopling.merge(meldinger,left_on='meldingsrad',right_index=True,validate='one_to_one')

# UTC-felta kan vere ISO-tekst eller millisekund. Omrekn til norsk dato.
def les_tid(verdi):
    if isinstance(verdi,(int,float)):
        return pd.to_datetime(verdi,unit='ms',utc=True,errors='coerce')
    return pd.to_datetime(verdi,utc=True,errors='coerce')
vegmeldinger['dato'] = vegmeldinger.FROM_DATE_UTC.map(les_tid).dt.tz_convert('Europe/Oslo').dt.date
display(vegmeldinger[['strekning_id','dato','avstand_m','NAME','MSG_DESCRIPTION','FREE_TEXT']].head(10))
print('Meldingsrader nær Rv13 i Vestland:',len(vegmeldinger))
''')
md('''## 7. Kople meldingsoversikta til strekningsdatasettet

Me tel meldingsrader per strekning og bruker `merge` til å leggje talet inn
i vegtabellen. Ein venstre-kopling beheld også strekningar utan meldingar.
Null betyr ingen melding som passerte dette filteret i perioden.

Det er **meldingsrader**, ikkje skred, episodar eller positive døgn.
''')
code('''antall = vegmeldinger.groupby('strekning_id').size().rename('vegmeldingsrader').reset_index()
strekninger = strekninger.merge(antall,on='strekning_id',how='left',validate='one_to_one')
strekninger['vegmeldingsrader'] = strekninger.vegmeldingsrader.fillna(0).astype(int)
display(strekninger[['strekning_id','lengde_km','vegmeldingsrader']])
fig,ax = plt.subplots(figsize=(7,9))
tegn_linje(ax,hele_vegen,color='#8297a3',linewidth=1)
ax.scatter(vegmeldinger.x,vegmeldinger.y,s=10,color='#cc6437',label='Meldingspunkt',zorder=3)
ax.set_aspect('equal'); ax.legend()
ax.set(title='Rv13 og vegmeldingar',xlabel='Aust (meter)',ylabel='Nord (meter)')
fig.tight_layout(); plt.show()
''')
md('''## 8. Lag ein 2 km-buffer

`linje.buffer(2000)` lagar ei flate som strekkjer seg opptil 2 km ut frå
veglinja i alle retningar. Det betyr om lag 4 km breidd langs ein rett veg.
Me gjer dette for kvar strekning, i eit koordinatsystem med meter.

Bufferane kan overlappe. Ei gridcelle kan derfor høyre til fleire strekningar.
''')
code('''buffere = [linje.buffer(BUFFER_METER) for linje in linjer]
VIS_STREKNING = 32
vis_index = strekninger.index[strekninger.strekning.eq(VIS_STREKNING)][0] if VIS_STREKNING in strekninger.strekning.values else 0
valgt_buffer = buffere[vis_index]
valgt_linje = linjer[vis_index]
fig,ax = plt.subplots(figsize=(8,6))
flater = [valgt_buffer] if valgt_buffer.geom_type=='Polygon' else list(valgt_buffer.geoms)
for flate in flater:
    x,y = flate.exterior.xy
    ax.fill(x,y,color='#9dc8d8',alpha=0.55)
tegn_linje(ax,valgt_linje,color='#cc6437',linewidth=2)
ax.set_aspect('equal')
ax.set(title=f'2 km-buffer: {strekninger.iloc[vis_index].strekning_id}',xlabel='Aust (meter)',ylabel='Nord (meter)')
fig.tight_layout(); plt.show()
''')
md('''## 9. Finn NVE-gridceller som overlappar bufferane

Me bruker det same 1 km-gridet som i prosjektet: EPSG:25833, vestkant
−75 000 m, nordkant 8 000 000 m og 1 195 kolonnar. Dette er ein bestemt
griddefinisjon, ikkje eit vilkårleg rutenett teikna rundt vegen.

Rad 0 er øvst, og kolonne 0 er lengst vest. Celle-ID-en er:

`cell_index = rad * 1195 + kolonne`

For kvar buffer finn me først moglege rader/kolonnar frå utstrekninga.
Så lagar me firkantane med `box` og beheld berre celler med positivt
overlappsareal. Cellene sin **midtkoordinat** kan seinare brukast til GTS-oppslag.
''')
code('''CELLE_METER = 1000
VEST = -75000
NORD = 8000000
KOLONNER = 1195
RADER = 1550
grid_rader = []
for i,buffer in enumerate(buffere):
    xmin,ymin,xmax,ymax = buffer.bounds
    kol_fra = max(0,math.floor((xmin-VEST)/CELLE_METER))
    kol_til = min(KOLONNER-1,math.floor((xmax-VEST)/CELLE_METER))
    rad_fra = max(0,math.floor((NORD-ymax)/CELLE_METER))
    rad_til = min(RADER-1,math.floor((NORD-ymin)/CELLE_METER))
    for rad in range(rad_fra,rad_til+1):
        for kol in range(kol_fra,kol_til+1):
            x = VEST + kol*CELLE_METER
            y = NORD - (rad+1)*CELLE_METER
            celle = box(x,y,x+CELLE_METER,y+CELLE_METER)
            areal = buffer.intersection(celle).area
            if areal > 0:
                grid_rader.append({'strekning_id':strekninger.iloc[i].strekning_id,
                    'cell_index':rad*KOLONNER+kol,'rad':rad,'kolonne':kol,
                    'x_midten':x+500,'y_midten':y+500,'overlapp_m2':areal,
                    'andel_av_buffer':areal/buffer.area})
grid = pd.DataFrame(grid_rader)
grid_antall = grid.groupby('strekning_id').size().rename('gridceller').reset_index()
strekninger = strekninger.merge(grid_antall,on='strekning_id',validate='one_to_one')
display(grid.head())
display(strekninger[['strekning_id','lengde_km','vegmeldingsrader','gridceller']])
print('Unike celler for heile vegutvalet:',grid.cell_index.nunique())
''')
md('''## 10. Teikn buffer, veg og grid saman

Kartet viser ei vald strekning. Firkantane er heile gridceller, medan
berre delen som overlappar bufferflata blir rekna med i `overlapp_m2`.

Ei geografisk celle er ikkje automatisk ei celle med tilgjengeleg vêrdata.
NVE har ei datamaske; dette må kontrollerast når me seinare hentar vêr.
Viss den tidlegare kontrollerte masketabellen finst i prosjektet, viser
me støtta celler i tabellen, utan å hente nokon vêrseriar her.
''')
code('''valgte_celler = grid.loc[grid.strekning_id.eq(strekninger.iloc[vis_index].strekning_id)]
fig,ax = plt.subplots(figsize=(8,7))
for flate in flater:
    x,y = flate.exterior.xy
    ax.fill(x,y,color='#9dc8d8',alpha=0.4)
for celle in valgte_celler.itertuples():
    firkant = box(celle.x_midten-500,celle.y_midten-500,celle.x_midten+500,celle.y_midten+500)
    x,y = firkant.exterior.xy
    ax.plot(x,y,color='#657f8c',linewidth=0.7)
tegn_linje(ax,valgt_linje,color='#cc6437',linewidth=2)
ax.set_aspect('equal')
ax.set(title='Rv13-strekning med 2 km-buffer og 1 km-celler',xlabel='Aust (meter)',ylabel='Nord (meter)')
fig.tight_layout(); fig.savefig(MAPPE/'rv13_buffer_grid.png',dpi=150); plt.show()

maskefil = ROOT/'data/processed/nve_gridceller_med_maske.csv'
if maskefil.exists():
    mask = pd.read_csv(maskefil)
    grid = grid.merge(mask[['cell_index','outside_nve_mask']],on='cell_index',how='left',validate='many_to_one')
    grid['nve_data_stottet'] = (~grid.outside_nve_mask.astype('boolean'))
    grid = grid.drop(columns='outside_nve_mask')
    display(grid.nve_data_stottet.value_counts(dropna=False).rename('strekning–celle-koplingar'))
else:
    print('NVE-datastøtte er ikkje kontrollert i dette dømet')
''')
md('''## 11. Lagre tabellane og gjer nokre enkle kontrollar

Tre CSV-filer viser resultatet:

- `rv13_strekninger.csv`: éi rad per strekning, med meldingsrad- og gridcelletal.
- `rv13_vegmeldinger.csv`: meldingskandidatar med vald strekning og avstand.
- `rv13_strekning_grid.csv`: éi rad per strekning–celle-kopling.

Ei melding nær ei strekningsgrense kan ha fleire moglege koplingar; denne
enkle notebooken vel berre den næraste. Historiske nummer, lange stengingar
og episodar krev fleire kontrollar før me kan lage ML-etikettar.
''')
code('''assert strekninger.strekning_id.is_unique
assert strekninger.vegmeldingsrader.sum()==len(vegmeldinger)
assert vegmeldinger.strekning_id.isin(strekninger.strekning_id).all()
assert grid.strekning_id.isin(strekninger.strekning_id).all()
assert not grid.duplicated(['strekning_id','cell_index']).any()
assert (grid.groupby('strekning_id').andel_av_buffer.sum()-1).abs().max()<0.000001
strekninger.to_csv(MAPPE/'rv13_strekninger.csv',index=False,encoding='utf-8-sig')
vegmeldinger.to_csv(MAPPE/'rv13_vegmeldinger.csv',index=False,encoding='utf-8-sig')
grid.to_csv(MAPPE/'rv13_strekning_grid.csv',index=False,encoding='utf-8-sig')
print('Lagra strekningar:',len(strekninger))
print('Lagra vegmeldingsrader:',len(vegmeldinger))
print('Lagra strekning–celle-koplingar:',len(grid))
print('Enkle kontrollar passerte')
''')
md('''## Prøv sjølv

1. Byt `VIS_STREKNING` og køyr bufferkartet og gridkartet på nytt.
2. Endre buffer frå 2 000 til 1 000 meter. Kor mange færre celler får du?
3. Endre `MELDING_AVSTAND_METER` frå 1 000 til 100. Kva meldingar blir borte?
4. Endre åra i første celle og køyr notebooken ovanfrå. Eldre år kan ha gamle nummer.
5. Vel ein tekst i `vegmeldinger`. Er ho faktisk skred, fare, opning eller noko anna?

Kjelder:

- [NVDB API Les V4](https://nvdb-docs.atlas.vegvesen.no/nvdbapil/v4/Vegnett/)
- [Xgeo vegmeldingslaget](https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer/13)
- [NVE pysenorge](https://github.com/NVE/pysenorge)

No har me vegstrekningar, meldingskandidatar og gridcellekoordinat.
Neste læringssteg kan vere å hente éin vêrparameter for éi celle og éin kort periode.
''')
for i,c in enumerate(cells):
    c['id']=f'rv13-basic-{i:03d}'
nb=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python (aktsomhet)',language='python',name='python3'),
    language_info=dict(name='python',version='3.12')),nbformat=4,nbformat_minor=5)
path=ROOT/'notebooks/rv13_enkel_dataarbeid.ipynb'
path.write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
print(path)
