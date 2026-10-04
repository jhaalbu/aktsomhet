# Skred og griddvêr: første 20-årsuttak

Analyseperioden er **2006-10-04 til 2026-10-03**, begge dagar inkluderte.
Det gir **7 305 døgn × 957 strekningar = 6 990 885 rader** i den samla tabellen.
Skreduttaket inneheld 16 634 hendingar i perioden. Av desse er 16 156 kopla
til 776 strekningar, og 478 er utan treff i dette vegnettsuttaket.
Vêr blir også henta for 2. og 3. oktober 2006 for å kunne rekne tre-døgnssummar
frå første analysedag. Vind blir berre etterspurt frå katalogstarten i 2010;
den faktiske første dagen med verdiar blir målt i kvalitetsrapporten.

Uttaket og valideringa er fullførte. Den samla tabellen har 46 kolonnar og
tek om lag 498 MB i Parquet. Med rådata, celleseriar og mellomtabellar tek
prosjektdataa om lag 3,26 GB.

| Parameter | Første gyldige dato | Manglande strekning–døgn |
|---|---|---|
| Nedbør | 2006-10-04 | 0,10 % |
| Nysnødjupn | 2006-10-04 | 0,10 % |
| Temperatur | 2006-10-04 | 0,10 % |
| Snødjupn | 2006-10-04 | 0,15 % |
| Vindretning | 2013-01-01 | 31,31 % |
| Vindhastigheit | 2013-01-01 | 31,30 % |
| Vassmetning i jord, etter kontrollregel | 2006-10-04 | 5,29 % |

Vind har altså ikkje gyldige verdiar for heile 20-årsperioden. Strekninga
`46_FV5664_S1` manglar støtta NVE-celler i bufferen, og har manglande vêrverdiar.
Ho er behalden i tabellen. 80 888 jordmetningsverdiar på cellenivå vart
utelatne av den dokumenterte 0–100 %-regelen.

Valideringa kontrollerte komplett døgnkalender og unike nøklar, bevarte
hendingsteljingar, direkte arealvekta utrekning frå celleseriar, maksimum,
tre-døgnssummar og lagging, sirkulært vindgjennomsnitt og jordmetningsintervallet.
Resultatet ligg i `data/weather/validation_report.json`.

Eit lite uttak kan lesast slik:

```python
import pandas as pd

df = pd.read_parquet(
    "data/weather/strekning_dogn/2025.parquet",
    filters=[("strekning_id", "==", "46_EV134_S10")],
)
print(df[["dato", "nedbor_mm_sum3d_lag1", "nysnodjupn_cm_sum3d_lag1", "registrerte_skred"]])
```

## Skredregisteringar

NVDB-objekttype **445, Skred** er henta for fylke 46, utan datofilter på
oppretting eller endring. Uttaket er filtrert lokalt på eigenskap **2324,
Skred dato**. Alle skredtypar er med; snøskred er ikkje blanda saman med
steinskred i teljingane etter skredtype.

- `data/processed/skred.csv`: éi rad per skredobjekt i analyseperioden.
- `data/processed/skred_strekning.csv`: referansar frå skred til strekning.
- `data/processed/skred_ukopla.csv`: referansar utan treff i vegnettsuttaket.
- `data/processed/skred_dogn.parquet`: tal på unike registrerte hendingar
  per strekning og dato, for datoar med minst ei hending.
- `data/processed/strekningar_med_skred.csv`: vegtabellen med total hendingsteljing.
- `data/processed/skred_kvalitetsrapport.json`: dekning, skredtypar og koplingstal.

Hendingar kan ha fleire vegreferansar. Teljing per strekning/dato brukar unike
skred-ID-ar, slik at fleire delstrekningstreff ikkje gir fleire hendingar.
Ei hending som treff fleire strekningar blir telt på kvar av dei.
Skred på sideanlegg eller kryss kan koplast til foreldre-strekninga, og er
merkte i referansetabellen. Vegnettsuttaket gjeld framleis E/R/F-vegar;
skred på andre vegkategoriar kan derfor hamne utan treff.

Koplinga brukar NVDB sine **noverande** vegreferansar. Ho rekonstruerer ikkje
vegnettet slik det var på hendingstidspunktet. Omnummereringar, nye vegar,
flytta geometri, endra fylkesgrenser og sletta objekt krev særskild kontroll
før historiske slutningar. Ingen geografisk nærleiksfallback tvingar ukopla
hendingar til nærmaste veg.

## Buffer og grid

`strekning_buffer_2km.parquet` inneheld faktiske polygonbufferar på **2 000 m**
rundt linjegeometrien til kvar NVDB-strekning, med WKB og EPSG:25833.
Geometrien frå NVDB EPSG:5973 blir strippa for høgd og transformert frå sitt
horisontale CRS til EPSG:25833. Dei same strekningane som i første uttak er
brukte, inkludert armar og eventuelle ferjestrekningar. Bufferar kan derfor
omfatte fjordareal; dei er geografiske nærområde, ikkje modellerte losneområde
eller nedbørfelt. Tunnelstrekningar er heller ikkje skilde ut enno.

NVE sitt seNorge-grid har 1 000 m store celler, med nordvestleg opphav
(-75 000, 8 000 000) og 1 195 kolonnar × 1 550 rader. Celleindeks er
nullbasert `rad * 1195 + kolonne`. Førespurnader brukar **cellesenter**,
slik at tvitydige koordinatar på cellegrenser blir unngått. Indeksane er
kontrollerte mot GTS-svar og NVE si offisielle gridcelleteneste.

- `strekning_grid_2km.parquet`: strekning–celle-kopling, areal av kvar
  gridcelle inne i bufferen, og vekta `intersection_m2 / buffer_area_m2`.
- `nve_gridceller.csv`: alle celler som overlappar bufferen med positivt areal.
- `nve_gridceller_med_maske.csv`: tillegg som viser celler utan GTS-dekning.
- `strekning_nve_dekning.csv`: delen av bufferarealet med støtta NVE-celler.

Bufferane treff 22 807 unike gridceller. Etter kontroll mot dagens API har
17 920 av desse støtte i nedbørproduktet; 4 887 manglar støtte. Andre produkt
kan ha ytterlegare manglande celler eller datoar, som blir rapporterte separat.

Ei publisert NVE-maske er brukt som utgangspunkt. **Alle** bufferceller som
ligg utanfor denne maska blir kontrollerte mot dagens nedbør-API før dei
eventuelt blir utelatne. Desse kontrollsvara blir lagra. Produkt som ikkje
støttar ei celle blir merkte separat, framfor å gi verdien null.

## Parameterar

Alle valde kjeldeseriar har **1440 minutt** tidsoppløysing.

| Parameter | GTS-tema | Eining i det behandla datasettet |
|---|---|---|
| Nedbør | `rr` | mm per døgn |
| Nysnødjupn | `sdfsw` | cm per døgn |
| Temperatur | `tm` | °C |
| Snødjupn | `sd` | cm |
| Vindretning, 10 m | `windDirection10m24h06` | grader |
| Vindhastigheit, 10 m | `windSpeed10m24h06` | m/s |
| Vassmetning i jord | `gwb_sssrel` | % |

Seriane er frå det menneskelesbare GTS-endepunktet, ikkje `/raw`; temperatur
skal derfor ikkje konverterast frå Kelvin ein gong til, og snø skal ikkje
delast på 10 ein gong til. Einingar frå faktiske svar blir bevarte i
batchmetadata og kontrollrapporten. Vindretningseininga er tom i API-katalogen;
retningane blir tolka som grader (0–360), og intervallet blir kontrollert.

Nysnødjupn i cm er ikkje det same som nysnøens vassekvivalent i mm, og ein
tre-døgnssum av nysnødjupn er ikkje netto endring i snøpakken etter setjing
og smelting. Jordparameteren er **modellert relativ vassmetning**, ikkje ei
feltmåling av volumetrisk vassinnhald.

Kjeldekontrollen fann mellom anna 16 760 % jordmetning 17.–18. juni 2022,
og tilsvarande svært høge verdiar 6.–7. januar 2024. Dei er også til stades
i NVE sitt punkt- og rådata-API. I den **behandla** tabellen blir verdiar
utanfor 0–100 % sette til manglande som ein konservativ fysisk kontrollregel.
Dette er vår behandlingsregel, ikkje NVE sin `NoDataValue`. Alle originalverdiar
er bevarte i celleseriane, og utelatne verdiar er lista i
`data/weather/gwb_sssrel_invalid_values.csv`. Ingen verdiar blir klipte til 100 %.

## Lagring og aggregering

Cellene blir lasta ned éin gong per tema og periode i små batchar. Overlapp
mellom strekningar gir ikkje duplikatnedlasting av same celleserie.

- `data/raw/nve/series/<tema>/*.json.gz`: komprimerte API-svar.
- `data/weather/cells/<tema>/*.parquet`: døgnseriar, éi kolonne per celle.
- Tilhøyrande `.json`: eksakt førespurnad, einingar, tidspunkt, SHA256,
  datodekning, gyldige verdiar og celler som ikkje er støtta av produktet.
- `data/weather/download_report.json`: status for heile uttaket. `complete`
  må vere `true` før endeleg aggregering blir køyrd.
- `data/weather/aggregated/`: aggregerte parameterar per strekning/døgn/år.
- `data/weather/strekning_dogn/<år>.parquet`: endeleg samla tabell,
  med **éin rad per strekning og døgn**, vêr og registrerte skred.
- `data/weather/eksempel_strekning_dogn.csv`: eit mindre lesbart eksempel.
- `data/weather/aggregation_report.json` og `dataset_report.json`: kvalitet og omfang.

For nedbør, snø, temperatur, vindhastigheit og jordmetning blir middelverdien
vekta med cellearealet inne i bufferen. Maksimum over overlappande celler er
også med. Manglande verdiar blir haldne utanfor summane; vektene blir
normaliserte over dei gyldige cellene den dagen. Verdiar blir sette til
manglande dersom mindre enn 80 % av det NVE-støtta landarealet har data.
`*_valid_fraction_land` viser dekninga i landarealet, medan
`nve_land_area_fraction` viser kor mykje av heile bufferen som er støtta.

Vindretning blir aggregert med arealvekte sinus- og cosinuskomponentar.
`vindretning_grader_resultant` ligg mellom 0 og 1 og viser kor samstemte
retningane er. Nær null betyr at eit gjennomsnitt har svak retning;
ved praktisk full kansellering blir gjennomsnittsretninga manglande.

Nedbør og nysnødjupn får `*_sum3d`: summen av analysedagen og dei to
føregåande dagane. Alle tre dagane må ha gyldige middelverdiar.
`*_sum3d_lag1` brukar berre dei tre dagane **før** analysedagen.
Alle parameterar får også `*_lag1`, førre dags middelverdi.
Den første analysedagen har manglande `*_sum3d_lag1`, sidan tre dagar før
den datoen ikkje er med i oppvarmingsperioden.

Datoane følgjer GTS sine etikettar. Punktendepunktet kan vise kl. 06 for
nedbør, medan batchendepunktet viser kl. 00. Dette uttaket harmoniserer
kalenderetikettar, og føreset ikkje at alle parameterar representerer same
fysiske tidsintervall 00–24. Eksakte meteorologiske døgn og tidspunkt for
tilgjengelege data må avklarast før operativ prognosering.

## ML-bruk

`registrerte_skred` er talet på registrerte hendingar i dette NVDB-uttaket.
`registrert_skred` er 0/1. Eigne `skred_<type>_antal` skil mellom skredtypar.
Ein null betyr **ingen registrert hending**, ikkje dokumentert fråvær av skred.
Registreringspraksis og dekning varierer over tid og mellom vegar.

Ver forsiktig med vêr på same dato som ei hending: ein del av vêret kan kome
etter skredet. Lagga variablar er inkluderte for modellar som skal predikere
før analysedagen. Total skredteljing for heile 20-årsperioden i
`strekningar_med_skred.csv` må ikkje brukast som ein vanleg prediktor for
historiske datoar; det ville lekke framtidige hendingar inn i modellen.

## Køyring

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/hent_skred.py
.venv/Scripts/python.exe scripts/lag_buffer.py
.venv/Scripts/python.exe scripts/hent_nve_metadata.py
.venv/Scripts/python.exe scripts/kontroller_gridmaske.py
.venv/Scripts/python.exe scripts/hent_ver.py
.venv/Scripts/python.exe scripts/aggreger_ver.py
.venv/Scripts/python.exe scripts/valider_datasett.py
```

Metadata-skriptet hentar `themes.json` og `norway_mask.npy` frå NVE og lagrar
kjelde-URL, tidspunkt og SHA256. Desse er lagra i dette uttaket.
Vêrsdownloaden kan køyrast på nytt for å fortsetje eit avbrote uttak;
fullførte batchar med identisk førespurnad blir brukte om att.
For ny periode må ein endre datoane i skripta og køyre heile kjeda på nytt.
Ikkje køyr fleire nedlastingar mot same outputkatalog samtidig.

## Kjelder

- Statens vegvesen, NVDB API Les V4, objekttype 445.
  https://nvdb-docs.atlas.vegvesen.no/nvdbapil/v4/Vegobjekter/
- NVE, GTS-dokumentasjon og metadata.
  https://api.nve.no/doc/gridtimeseries-data-gts/
- NVE, griddefinisjon og publisert maske.
  https://github.com/NVE/pysenorge/blob/master/pysenorge/doc/SeNorgeGrid.txt
  https://github.com/NVE/pysenorge/blob/master/pysenorge/resources/norway_mask.npy
- NVE, gridcelleteneste.
  https://gis3.nve.no/arcgis/rest/services/geoprocessing/SeNorgeCeller/GPServer/SeNorgeCeller

GTS-data blir tilbydde under NLOD / CC BY 3.0 Norge. Krediter NVE og dei
underliggjande dataleverandørane ved vidare bruk og deling.
