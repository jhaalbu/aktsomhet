"""Build the project's learning notebook without requiring notebook libraries."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cells = []


def md(s):
    cells.append(dict(cell_type='markdown', metadata={}, source=s.strip().splitlines(keepends=True)))


def code(s):
    cells.append(dict(cell_type='code', metadata={}, execution_count=None, outputs=[],
                      source=s.strip().splitlines(keepends=True)))


md('''# Frå vegnett til skredmodell i Vestland
Ein praktisk gjennomgang for eiga læring. Køyr cellene ovanfrå og ned.

**Spørsmålet:** Kan tidlegare vêr og veginformasjon hjelpe oss å rangere
strekningar etter om dei får minst eitt **registrert** skred neste kalenderdato?

Løpet er: NVDB-vegnett → skred og kopling → 2 km-buffer → NVE-grid og døgnvêr
→ kvalitet og variablar → tidsdeling → referansemodell og LightGBM
→ kalibrering → sluttest og geografisk kontroll.

Standardkøyringa les eksisterande filer og trenar ein liten demonstrasjonsmodell
i minnet. Ho lastar ikkje ned data eller skriv over første modellrunde.
Demonstrasjonen bruker færre år enn den fullstendige modellen; resultata er derfor
ikkje direkte samanliknbare. Dei fullstendige resultata blir gjennomgått separat.

## Før du byrjar
Vel Python-kjernen frå prosjektet si `.venv` i Jupyter eller VS Code.
Om du manglar Jupyter, køyr desse kommandoane i ein terminal i prosjektmappa:

```powershell
.venv/Scripts/python.exe -m pip install notebook ipykernel
.venv/Scripts/python.exe -m ipykernel install --user --name aktsomhet --display-name "Python (aktsomhet)"
.venv/Scripts/python.exe -m notebook notebooks/skred_ml_laering.ipynb
```

Prosjektpakkane ligg i `requirements.txt`. Jupyter er eit ekstra visingsverktøy.
Filer og versjonar er dokumenterte i [DATA.md](../DATA.md) og [MODEL.md](../MODEL.md).
''')
code('''from pathlib import Path
import os, sys, json, subprocess
ROOT = next((p for p in [Path.cwd(), *Path.cwd().parents]
             if (p / 'scripts/tren_modell.py').exists()), None)
assert ROOT is not None, 'Start notebooken frå prosjektmappa eller notebooks/'
os.environ['MPLCONFIGDIR'] = str(ROOT / 'models/.mplcache')
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display
SEED = 20261004
def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8-sig'))
print('Prosjekt:', ROOT)
print('Python:', sys.executable)
''')
md('''## 1. Hente vegnettet frå NVDB
Uttaket gjeld fylke 46 og eksisterande E-, R- og F-vegar. Skriptet hentar
alle sider frå API-et og bevarer råsvar og SHA256-hashar. Paginering er nødvendig:
den første API-sida er berre ein del av vegnettet.

Vegnummer åleine er ikkje ein unik nøkkel. Me brukar fylke, kategori, fase,
vegnummer og strekning, til dømes `46_EV16_S1`. Delstrekningar og segment
blir samla til strekningar. Desse er administrative NVDB-einingar;
lengdene varierer og er **ikkje faste 10 km**.

Koden under viser førespurnaden, utan å sende han. Produksjonsskriptet er
`scripts/hent_nvdb.py`. Historiske skred blir kopla til dette daterte,
noverande vegnettsuttaket; me har ikkje rekonstruert historiske vegreferansar.
''')
code('''from urllib.parse import urlencode
nvdb_url = 'https://nvdbapiles.atlas.vegvesen.no/vegnett/api/v4/veglenkesekvenser/segmentert'
print(nvdb_url + '?' + urlencode(dict(fylke=46, vegsystemreferanse='EV,RV,FV', antall=1000)))
roads = pd.read_csv(ROOT / 'data/processed/strekningar.csv')
assert roads.strekning_id.is_unique
display(roads.head())
display((roads.lengde_m / 1000).describe().rename('lengde_km'))
''')
md('''## 2. Hente skred og lage etikettar
NVDB-objekttype **445** er Skred. Me filtrerer på eigenskap 2324, *Skred dato*,
ikkje datoen då objektet vart oppretta eller sist endra i registeret.
Perioden er 4. oktober 2006–3. oktober 2026.

Eitt skred kan ha fleire referansar til same strekning. Me tel unike skred-ID-ar
per strekning og dato. Eitt skred som treff to strekningar gir to positive
strekning-døgn. Ukopla hendingar blir bevarte for kontroll, ikkje tvinga til
nærmaste veg. Utfallet er `registrert_skred = registrerte_skred > 0`.

Ein null betyr **ingen registrert hending i uttaket**. Registeret dokumenterer
ikkje at ingen skred faktisk skjedde.
''')
code('''slides = pd.read_csv(ROOT / 'data/processed/skred.csv', parse_dates=['dato'])
links = pd.read_csv(ROOT / 'data/processed/skred_strekning.csv')
display(slides[['skred_id', 'dato', 'skredtype', 'match_antal']].head())
display(links.head())
display(slides.skredtype.value_counts().rename('registrerte_hendingar').to_frame())
print('Unike hendingar:', slides.skred_id.nunique())
print('Utan kopling:', int((slides.match_antal == 0).sum()))
''')
md('''## 3. Romleg beriking: buffer og gridceller
Me byggjer ein 2 000 meter-buffer rundt dei faktiske veglinjene i EPSG:25833,
eit koordinatsystem med meter som eining. Ein buffer i lengde-/breiddegrader
ville ikkje hatt denne avstanden. Geometrien blir transformert før bufferbygging.

Bufferen blir kryssa med NVE sine 1 km-celler. Bru-tabellen har éi rad per
strekning og celle. `intersection_m2` er arealet av cella inne i bufferen.
Bufferar kan overlappe; kvar celleserie blir likevel henta berre éin gong.
Bufferen kan innehalde fjord og er ikkje eit kartlagt losneområde.

For ein skalar som nedbør brukar me
`middel = sum(areal × celleverdi) / sum(gyldig areal)`.
Me krev minst 80 % gyldig dekning av NVE-støtta landareal den dagen.
Manglande celleverdi er ikkje null nedbør.
''')
code('''bridge = pd.read_parquet(ROOT / 'data/processed/strekning_grid_2km.parquet')
display(bridge.head())
print('Unike celler i bufferane:', bridge.cell_index.nunique())
# Lite rekneeksempel, ikkje faktiske målingar:
area = np.array([100_000., 300_000., 100_000.])
rain = np.array([10., 30., np.nan])
valid = np.isfinite(rain)
coverage = area[valid].sum() / area.sum()
mean = np.average(rain[valid], weights=area[valid]) if coverage >= .8 else np.nan
print(f'Gyldig areal: {coverage:.0%}; vekta nedbør: {mean:.1f} mm')
''')
md('''## 4. NVE Grid Time Series: døgnvêr
Nedlastinga brukar cellesenter og batchar, med 1 440 minutt tidsoppløysing.
Råsvar, einingar, datoar og førespurnader blir bevarte. Fullførte batchar
kan brukast om att etter avbrot. Skriptet `hent_ver.py` handterer sjølve uttaket.

| Variabel | Tema | Behandla eining |
|---|---|---|
| Nedbør | rr | mm/døgn |
| Nysnødjupn | sdfsw | cm/døgn |
| Temperatur | tm | °C |
| Snødjupn | sd | cm |
| Vindretning | windDirection10m24h06 | grader |
| Vindhastigheit | windSpeed10m24h06 | m/s |
| Modellert jordmetning | gwb_sssrel | % |

Nysnødjupn er ikkje vassekvivalent. Jordmetning er ein modellvariabel,
ikkje målt volumetrisk vassinnhald. Uttaket bruker det menneskelesbare
endepunktet, så me skal ikkje konvertere temperatur frå Kelvin eller snø
frå mm ein gong til. Vind har først gyldige data frå 2013.
''')
code('''# Inspiser ein eksakt, lagra batchførespurnad utan nettverk:
batch_file = next((ROOT / 'data/weather/cells/rr').glob('*.json'))
batch_metadata = json.loads(batch_file.read_text(encoding='utf-8'))
display(batch_metadata['request'])
display(read_json('data/weather/download_report.json'))
''')
md('''### Vindretning krev sirkulær statistikk
Vanleg gjennomsnitt av 350° og 10° er 180°, som peikar feil veg.
Me vekter sinus og cosinus, og finn vinkelen med `atan2`.
Resultant nær null betyr at retningane kansellerer kvarandre.
''')
code('''angles = np.deg2rad([350., 10.])
s, c = np.mean(np.sin(angles)), np.mean(np.cos(angles))
direction = np.rad2deg(np.arctan2(s, c)) % 360
if np.isclose(direction, 360): direction = 0.
print('Sirkulært middel:', direction, 'grader; resultant:', np.hypot(s, c))
''')
md('''## 5. Samla tabell og kvalitetskontroll
Sluttdatasettet har éi rad per strekning og døgn, fordelt på årlege Parquet-filer.
Me kontrollerer unike nøklar, komplett kalender, bevarte skredteljingar,
arealvekting, laggar og einingar. `valider_datasett.py` kontrollerer også mot
dei underliggjande celleseriane; berre å sjå på tabellen er ikkje tilstrekkeleg.

Nokre originale jordmetningsverdiar var utanfor 0–100 %. Vår dokumenterte
kontrollregel set dei til manglande i behandla data og bevarer originalane.
Ein strekning manglar støtta vêrceller og er framleis med i panelet.
''')
code('''sample = pd.read_parquet(ROOT / 'data/weather/strekning_dogn/2025.parquet')
assert not sample.duplicated(['strekning_id', 'dato']).any()
assert sample.groupby('dato').size().eq(len(roads)).all()
assert sample.registrert_skred.eq(sample.registrerte_skred.gt(0).astype(int)).all()
display(sample[['strekning_id', 'dato', 'nedbor_mm_lag1',
                'nedbor_mm_sum3d_lag1', 'registrerte_skred']].head())
display(sample[['nedbor_mm_lag1', 'vindhastigheit_ms_lag1',
                'jord_vassmetning_pct_lag1']].isna().mean().rename('manglande_andel'))
display(read_json('data/weather/validation_report.json'))
''')
md('''## 6. Variablar og datalekkasje
For måldato *t* brukar me berre tidlegare vêr. `lag1` er dato *t−1*;
`sum3d_lag1` er summen av *t−3*, *t−2* og *t−1*. Same-dagsvêr kan innehalde
vêr etter skredet. `sum3d` utan lag må derfor ikkje forvekslast med modellvariabelen.

Lagging må gjerast **innan kvar strekning**, etter sortering på dato.
Me les desember frå førre år for å få historikk ved nyttår. Eksemplet under
kontrollerer dei eksisterande tre-døgnssummane for éi strekning.
''')
code('''SID = '46_EV134_S10'
one = pd.concat([pd.read_parquet(ROOT / f'data/weather/strekning_dogn/{yr}.parquet',
                  filters=[('strekning_id', '==', SID)]) for yr in [2024, 2025]], ignore_index=True)
one = one.sort_values('dato').reset_index(drop=True)
one['rekna_sum3d_lag1'] = one.nedbor_mm_mean.shift(1).rolling(3, min_periods=3).sum()
check = one.dato.between('2025-01-01', '2025-12-31')
np.testing.assert_allclose(one.loc[check, 'rekna_sum3d_lag1'],
                           one.loc[check, 'nedbor_mm_sum3d_lag1'],
                           rtol=1e-5, atol=1e-5, equal_nan=True)
display(one.loc[check, ['dato', 'nedbor_mm_mean', 'nedbor_mm_lag1',
                        'nedbor_mm_sum3d_lag1', 'registrert_skred']].head(8))
''')
md('''Årstid og vind blir representerte med sinus/cosinus, slik at desember/januar
og 359°/1° ligg nær kvarandre. Den fullstendige modellen har 22 vêr-/sesongvariablar
og 4 vegvariablar. Skredteljingar frå heile perioden skal aldri brukast som
historisk prediktor: då ville framtidige hendingar lekke inn.

GTS sine kalenderetikettar er ikkje dokumentert som identiske meteorologiske
døgn eller tilgjengelege på same klokkeslett. Kalenderlagging er kontrollert,
men operativ tilgjengelegheit må avklarast før faktisk varsling.
''')
md('''## 7. Tidsdeling før trening
Tilfeldig radfordeling ville blande framtida inn i trening og leggje
nabostrekningar frå same vêrdøgn på begge sider. Første fulle modellrunde bruker:

| Del | År | Føremål |
|---|---|---|
| Trening | 2013–2020 | Tilpasse modell og historisk referanse |
| Validering | 2021–2022 | Tidleg stopp og modellval |
| Kalibrering | 2023 | Tilpasse sannsynsskala |
| Sluttest | 2024–3. oktober 2026 | Endeleg evaluering |

2012 gir oppvarming for laggar. Sluttesten er no undersøkt og må ikkje
brukast om att som ein urørt test etter mykje tuning mot resultata.
''')
code('''audit = read_json('models/first_run/data_audit.json')
display(pd.DataFrame(audit['splits']).T)
display(pd.Series(audit['weather_features'], name='fullstendige_vêrvariablar'))
''')
md('''## 8. Ei mindre trening du kan eksperimentere med
No trenar du ein **eigen demonstrasjon i minnet**, med 2019–2020 til trening,
2021 til validering, 2022 til kalibrering og 2023 til test. Alle strekningar
er med, og klassefordelinga blir bevart. Me brukar eit lite utval variablar
og opptil 100 tre for at dette skal vere lettare å prøve.

Historisk referanse blir tilpassa berre treningsdata. LightGBM kan lære
ikkje-lineære samanhengar og samspel, og handterer manglande verdiar direkte.
Me deler ikkje desse resultata som ei ny full modellrunde.
''')
code('''sys.path.insert(0, str(ROOT / 'scripts')) if str(ROOT / 'scripts') not in sys.path else None
import tren_modell as pipeline
import lightgbm as lgb
from sklearn.metrics import average_precision_score, brier_score_loss
features = ['nedbor_mm_lag1', 'nedbor_mm_sum3d_lag1',
            'nysnodjupn_cm_sum3d_lag1', 'temperatur_c_lag1',
            'snodjupn_cm_lag1', 'vindhastigheit_ms_lag1', 'jord_vassmetning_pct_lag1']
columns = ['strekning_id', 'dato', 'registrert_skred'] + features
demo = pd.concat([pd.read_parquet(ROOT / f'data/weather/strekning_dogn/{yr}.parquet',
                                columns=columns) for yr in range(2019, 2024)], ignore_index=True)
demo = demo.sort_values(['dato', 'strekning_id']).reset_index(drop=True)
keys = demo[['strekning_id', 'dato']].copy()
keys['month'] = keys.dato.dt.month
y = demo.registrert_skred.to_numpy()
X = demo[features].copy()
doy = demo.dato.dt.dayofyear
X['arstid_sin'] = np.sin(2*np.pi*doy/365.25)
X['arstid_cos'] = np.cos(2*np.pi*doy/365.25)
train = demo.dato.dt.year.le(2020).to_numpy()
val = demo.dato.dt.year.eq(2021).to_numpy()
cal = demo.dato.dt.year.eq(2022).to_numpy()
test = demo.dato.dt.year.eq(2023).to_numpy()
assert np.all(train.astype(int) + val + cal + test == 1)
display(pd.DataFrame([{'del': name, 'rader': int(m.sum()), 'positive': int(y[m].sum())}
                     for name, m in [('trening', train), ('validering', val),
                                     ('kalibrering', cal), ('test', test)]]))
history = pipeline.history_fit(keys, y, train)
model = lgb.LGBMClassifier(**{**pipeline.PARAMS, 'n_estimators': 100, 'n_jobs': 4})
model.fit(X.loc[train], y[train], eval_set=[(X.loc[val], y[val])],
          callbacks=[lgb.early_stopping(20, verbose=False)])
print('Valt tal tre:', model.best_iteration_)
''')
md('''## 9. Kalibrering og evaluering av demonstrasjonen
Ei rangering kan vere nyttig utan at skårane er gode sannsyn.
Sigmoidkalibrering tilpassar skalaen på eit separat år. Ho skal ikkje
tilpassast på testdata. Kalibreringsåret er ikkje ein uavhengig test.

Me samanliknar average precision (AP), Brier og topp 10 per dag.
Recall ved topp 10 er delen av positive strekning-døgn som blir fanga.
Precision ved topp 10 er delen av flagga som har registrert skred.
Ved sjeldne hendingar kan ein modell få over 99 % accuracy ved å seie
«ingen skred» kvar dag; accuracy er derfor eit dårleg hovudmål her.
''')
code('''raw_cal = model.predict_proba(X.loc[cal])[:, 1]
calibration = pipeline.calibrated(raw_cal, y[cal])
raw_test = model.predict_proba(X.loc[test])[:, 1]
demo_score = pipeline.apply_cal(raw_test, calibration)
history_cal = pipeline.calibrated(pipeline.history_predict(history, keys.loc[cal]), y[cal])
history_score = pipeline.apply_cal(pipeline.history_predict(history, keys.loc[test]), history_cal)
def summary(score, name):
    ranked = keys.loc[test, ['strekning_id', 'dato']].copy()
    ranked['y'], ranked['score'] = y[test], score
    # Same seeded tie order for both models; avoid alphabetical preference.
    ids = sorted(ranked.strekning_id.unique())
    tie = dict(zip(ids, np.random.default_rng(SEED).permutation(len(ids))))
    ranked['tie'] = ranked.strekning_id.map(tie)
    top = ranked.sort_values(['dato', 'score', 'tie'], ascending=[True, False, True]).groupby('dato').head(10)
    return dict(modell=name, AP=average_precision_score(y[test], score),
                Brier=brier_score_loss(y[test], score),
                recall_topp10=top.y.sum()/y[test].sum(), precision_topp10=top.y.mean())
demo_metrics = pd.DataFrame([summary(history_score, 'Historisk referanse'),
                             summary(demo_score, 'Liten vêrmodell')])
display(demo_metrics)
print('Grunnfrekvens i demonstrasjonstesten:', y[test].mean())
''')
md('''## 10. Dei lagra resultata frå den fullstendige modellen
Dette er den faktiske første modellrunden med tidsdelinga frå kapittel 7,
ikkje demonstrasjonen. Vêr og veg vart valt på valideringsdata.
Sluttesten viser ingen dokumentert gevinst ved ti daglege flagg:
174 positive døgn mot referansen sine 176, av 2 501 positive døgn totalt.
Betre AP treng ikkje bety betre topp 10; måla vurderer ulike delar av rangeringa.
''')
code('''metrics = pd.read_csv(ROOT / 'models/first_run/temporal/metrics.csv')
display(metrics.loc[metrics['split'].eq('test'),
                    ['model', 'average_precision', 'true_positive_top10',
                     'recall_top10', 'precision_top10', 'brier']])
from IPython.display import Image
display(Image(filename=str(ROOT / 'models/first_run/temporal/evaluation.png')))
''')
md('''### Sjå på prediksjonane for ein dato
Topp 10 er eit fast dagleg budsjett, ikkje ein sannsynsterskel. Det vil flagge
ti strekningar også på dagar med låg skår. Vel ein annan dato for å utforske.
''')
code('''DATE = '2025-01-01'
pred = pd.read_parquet(ROOT / 'models/first_run/temporal/weather_and_road_test_predictions.parquet')
display(pred.loc[pred.dato.eq(pd.Timestamp(DATE))].sort_values('score', ascending=False).head(10))
importance = pd.read_csv(ROOT / 'models/first_run/temporal/weather_and_road_importance.csv')
display(importance.head(10))
''')
md('''Gain-fordelinga viser at strekningsidentiteten dominerer den første kombinerte
modellen. Gain er ikkje eit kausalt mål og kan favoriserast av kategoriske
variablar. Det viser kva modellen brukar i splittingane, ikkje at vegnummer
eller ei bestemt vêrvariabel i seg sjølv forårsakar skred.

## 11. Usikkerheit og geografisk kontroll
Nabodagar deler vêr og skredhendingar. Vanleg bootstrap av enkelt­rader ville
behandle desse som uavhengige. Me trekkjer kalender-månadsblokker, med same
blokker for begge modellar, og samanliknar recall. Første runde brukte 1 000
trekningar. Intervallet for endringa mot historisk referanse er −0,92 til
+0,69 prosentpoeng: det støttar ikkje ein sikker gevinst.

Dette intervallet gjeld faste, ferdigtrena modellar; det dekkjer ikkje
usikkerheit frå ny trening eller manglande skredregistreringar.

Geografisk kontroll held 89 nordlege strekningar utanfor trening,
validering og kalibrering, og testar framtidige datoar i det nye området.
Ein 4 km avstand mellom strekningsboksane skil 2 km-bufferane.
Grensene vart valde frå koordinatar, utan å bruke skredetikettar.
''')
code('''display(read_json('models/first_run/temporal/bootstrap.json'))
geo = read_json('models/first_run/geographic/geography.json')
print('Haldne utanfor:', len(geo['held_section_ids']))
print('Treningsområdet:', len(geo['training_section_ids']))
gm = pd.read_csv(ROOT / 'models/first_run/geographic/metrics.csv')
display(gm.loc[gm['split'].eq('test'), ['model', 'positives', 'true_positive_top10', 'recall_top10']])
display(read_json('models/first_run/validation_report.json'))
''')
md('''Den geografiske kontrollen gav eit positivt resultat for vêr og veg, men berre
i eitt område. Topp 10 av 89 strekningar er eit langt større utval enn topp 10
av 957. Desse recall-tala kan derfor ikkje samanliknast direkte.

## 12. Køyre heile produksjonsløpet på nytt
Desse cellene er **av som standard**. Dei viser eksakt rekkjefølgje og brukar
den same Python-kjernen som notebooken. Nedlastinga kan vere stor og skriv i
eksisterande datamapper. Modellskriptet skriv over `models/first_run`.
Ta kopi av data/resultat før eit nytt uttak eller eksperiment.
Datoane ligg i skripta og må endrast samordna ved ein ny periode.
''')
code('''RUN_DOWNLOAD = False
RUN_TRAINING = False
RUN_VALIDATION = False
def run_script(name):
    subprocess.run([sys.executable, str(ROOT / 'scripts' / name)], cwd=ROOT, check=True)
if RUN_DOWNLOAD:
    for script in ['hent_nvdb.py', 'hent_skred.py', 'lag_buffer.py',
                   'hent_nve_metadata.py', 'kontroller_gridmaske.py',
                   'hent_ver.py', 'aggreger_ver.py', 'valider_datasett.py']:
        run_script(script)
if RUN_TRAINING:
    run_script('tren_modell.py')
if RUN_VALIDATION:
    run_script('valider_datasett.py')
    run_script('valider_modell.py')
print('Produksjonsløpet køyrer berre når du set eit av vala til True.')
''')
md('''## 13. Aktsomheitsområde som romleg beriking
NVE-zipfila som vart lagt inn i prosjektet inneheld aktsomheitskart for
steinsprang, jord-/flaumskred og fleire snøskredvariantar. Skriptet
`kople_aktsomhet.py` les GeoJSON direkte frå zip, med strøymande JSON-lesing.
Filer i dette uttaket har eksplisitt EPSG:25833, ikkje lengde-/breiddegrader.

Me brukar det samla jord-/flaumlaget, både losne- og utløpsområde for steinsprang,
og snøskred S2 utan skogeffekt. S2/S3 er namn på kartvariantar frå arealplanlegging;
dei er ikkje klassar for risiko langs veg. Andre snøvariantar ligg framleis i råfila.

Overlappen blir rekna mot veglinjene, ikkje vêrbufferen. Overlappande polygon
blir ikkje dobbelttelte: me tek lokal union av polygon før veglinja blir
kryssa med dei. Nemnaren er geometrisk union-lengd, som kan avvike frå summert
NVDB-lengd. Ein eigen 20 m-regel er berre ein sensitivitetskontroll.

Originaldata er bevarte. `behald_direkte` er eit mogleg filter, medan meter
og andel innanfor kvart tema er moglege nye modellvariablar. Kontrollrapporten
viser kor mange registrerte skred filteret ville ha utelate. Dette er ikkje
ei ny modelltrening, og betre prediksjonsevne er ikkje demonstrert.

Karta er eit noverande uttak frå 2026 og kan byggje på seinare kunnskap enn
historiske måldatoar. Ingen overlapp er ikkje dokumentasjon på null skredfare.
Eit skred på ein behalden strekning er heller ikkje nødvendigvis inne i eit
polygon; kontrollen her er på strekningsnivå.
''')
code('''hazard_file = ROOT / 'data/processed/aktsomhet/strekning_aktsomhet.parquet'
if hazard_file.exists():
    hazard = pd.read_parquet(hazard_file)
    enriched_roads = roads.merge(hazard, on='strekning_id', validate='one_to_one')
    assert len(enriched_roads) == len(roads)
    display(enriched_roads[['strekning_id', 'stein_andel', 'jord_flaum_andel',
                            'sno_s2_utan_skog_andel', 'behald_direkte']].head())
    display(pd.DataFrame(read_json('data/processed/aktsomhet/rapport.json')['summaries']))
    display(pd.read_csv(ROOT / 'data/processed/aktsomhet/skredtype_filterkontroll.csv'))
else:
    print('Køyr scripts/kople_aktsomhet.py først for å lage denne berikinga.')
''')
md('''## 14. Historiske vegmeldingar: eit alternativt utfall
Me har lasta ned heile det tilgjengelege nasjonale laget `XgeoVeimelding2/13`
for meldingsdatoar til og med 3. oktober 2026: 105 407 postar. Årsvis
paginering, hashkontroll og teljing før/etter kvar årsfil gjer uttaket
etterprøvbart. Ingen meldingar vart funne i 2006–2009 i dette laget.

`filtrer_xgeo_vegmeldingar.py` finn geografiske kandidatar og skil tekst som
omtalar skred/nedfall frå rasfare, kontrollert utløsning, opning etter skred
og andre forhold. Skredtypane blir ikkje brukte som separate ML-etikettar.
Isnedfall er med i dette breie utfallet, slik det også er i NVDB-utfallet.

Det strenge kandidatutfallet krev same vegkategori og anten dagens nummer
eller eit dokumentert gammalt nummer i Vegvesenet sine reformlister.
Gamle fylke blir bestemt frå kommunen på den aktuelle veggeometrien.
For nummeromsetjinga tillèt me gamle alias til og med 2021; bruk etter
NVDB si endringsdato blir særskilt markert. Dette er ei overgangsregel,
ikkje eit eksakt oppslag av referansens gyldigheit på meldingsdatoen.
Meldingane manglar hovudparsell/meter, så koordinat skil mellom greinene
når ein gammal veg vart delt i fleire nye nummer.

Utvalet krev vidare eit eintydig
visingspunkt innan 100 m frå dagens veglinje, minst 20 m avstandsskilnad
til nest næraste strekning, og at eventuelle start-/sluttpunkt ikkje ligg
meir enn 100 m frå den valde strekninga. Dette er forsøksreglar, ikkje
verifisert stadnøyaktigheit. Kategoriendringar, vegomleggingar og eldre
omnummereringar utanfor reformlistene kan framleis gi manglande kopling.

Etter rettinga aukar positive strekning–døgn i 2013–2020 frå 311 til 599.
Eit positivt døgn er ein strekning/dato med minst éin behalden episode,
uavhengig av kor mange oppdateringar eller skred som er registrerte den dagen.

Oppdateringar med same situasjon og strekning blir samla i episodekandidatar.
Me deler ved eit opphald over sju døgn. Dette kan både slå saman to ulike
skred og dele ei langvarig hending; det må kontrollerast. Etikettdatoen er
den første positive meldingas gyldigheitsstart, ikkje stadfesta skredtid.

Dagstabellane tilbyr NVDB, Xgeo og unionen som tre utfall, utan å endre
originaldata. Null betyr ingen behalden melding, ikkje dokumentert skredfråvær.
Ein union av binære døgnetikettar gir berre éin positiv per strekning/dato;
det er ikkje det same som deduplisering av hendingar mellom kjeldene.
''')
code('''message_root = ROOT / 'data/processed/vegmeldingar'
if (message_root / 'filterrapport.json').exists():
    display(read_json('data/processed/vegmeldingar/filterrapport.json'))
    display(pd.read_csv(message_root / 'kjeldesamanlikning_per_ar.csv'))
    display(pd.read_csv(message_root / 'filtersteg_per_ar.csv'))
    if (message_root / 'historisk_kopling_per_ar.csv').exists():
        display(pd.read_csv(message_root / 'historisk_kopling_per_ar.csv'))
    # Kopling av alternative etikettar til det eksisterande vêrgrunnlaget:
    labels_2025 = pd.read_parquet(message_root / 'etikettar_dogn/2025.parquet')
    learning_2025 = sample.merge(
        labels_2025.drop(columns='registrert_skred'),
        on=['strekning_id','dato'], validate='one_to_one')
    assert len(learning_2025) == len(sample)
    display(learning_2025.loc[learning_2025.vegmelding_skred.eq(1),
        ['strekning_id','dato','registrert_skred','vegmelding_skred',
         'skred_ei_av_kjeldene','nedbor_mm_sum3d_lag1']].head())
else:
    print('Hent og filtrer vegmeldingane først; sjå VEGMELDINGAR_UTTAK.md.')
''')
md('''Utforsk `manuell_kontroll.csv`: kan du finne feil i teksten eller koplinga?
Utvalet er stratifisert på år, klasse og om meldinga oppfyller dei strenge
radreglane. Fyll inn `review_label` og `review_comment` i ei kopi.
Mål presisjon og kva faktiske skred som blir mista før du skiftar modellutfall.

Den første modellen vår brukte allereie alle NVDB-skredtypar samla.
Eitt samla utfall unngår usikker typeklassifisering, men blandar prosessar
som reagerer ulikt på vêr. Det garanterer ikkje betre prediksjonar.
Omnummerering forklarte ein del av det låge utvalet før 2021 og er no retta
med reformlistene og geografisk kontroll. Det er framleis færre eldre
melding­ar i kjelda, og eit lågare behalde utval må vurderast;
ein modell kan elles lære endra registreringspraksis.
''')
md('''## 15. Oppgåver for vidare læring
1. Byt `SID` og samanlikn vêr og registrerte skred på to strekningar.
2. Fjern nysnø frå demonstrasjonsmodellen. Endrar valideringsresultatet seg?
3. Rekn topp 5 og topp 50. Korleis endrar recall og precision seg?
4. Undersøk manglande jordmetning og kvifor nullutfylling ville gi feil meining.
5. Planlegg separate modellar for snøskred, steinsprang og jord-/flomskred.
   Definer nye etikettar og tidsvalidering før du ser på nye testresultat.
6. Planlegg terrengvariablar: helling, høgd og terrenget over vegane, og
   handtering av tunnelar og skredsikring. Ein 2 km-buffer er berre eit første grep.

Ved gjenteken eksperimentering blir teståret i demonstrasjonen utviklingsdata.
Bruk rullande tidsvalidering for modellval og reserver ein ny, definert sluttest.

### Kjelder og kode
- [NVDB API Les V4](https://nvdb-docs.atlas.vegvesen.no/nvdbapil/v4/Vegnett/)
- [NVE Grid Time Series](https://api.nve.no/doc/gridtimeseries-data-gts/)
- [LightGBM](https://lightgbm.readthedocs.io/en/stable/Python-API.html)
- [scikit-learn: average precision](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html)
- [Datadokumentasjon](../DATA.md), [modellrapport](../MODEL.md),
  [treningskode](../scripts/tren_modell.py), [uavhengig modellkontroll](../scripts/valider_modell.py).

Krediter NVDB/Statens vegvesen og NVE med underliggjande dataleverandørar ved vidare bruk.
''')

notebook = dict(cells=cells, metadata=dict(
    kernelspec=dict(display_name='Python (aktsomhet)', language='python', name='aktsomhet'),
    language_info=dict(name='python', version='3.12')), nbformat=4, nbformat_minor=5)
for i, cell in enumerate(cells):
    cell['id'] = f'laering-{i:02d}'
target = ROOT / 'notebooks/skred_ml_laering.ipynb'
target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding='utf-8')
print(target)
