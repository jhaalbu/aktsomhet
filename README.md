# Skredfare langs vegar i Vestland

For eit enklare læringsdøme: [Rv13 – enkelt dataarbeid](notebooks/rv13_enkel_dataarbeid.ipynb)
bruker berre Rv13 i Vestland og Xgeo-meldingar frå 2024–2025. All behandling
står direkte i cellene: API-henting, segmenttabell, strekningsgruppering,
meldingspunkt, 2 km-buffer og overlapp med NVE sitt 1 km-grid. Alle 12
kodecellene er køyrde. Dømet gir 26 strekningar, 1 169 meldingskandidatrader
og 1 163 unike geometriske gridceller. Oppdateringar er ikkje dedupliserte
til hendingar. Filer og kart ligg i `data/notebook/rv13_enkelt/`.

Første steg i eit ML-prosjekt: eit reproduserbart uttak av vegnett frå NVDB,
gruppert etter eksisterande vegnummer, strekning og delstrekning.

Skredregisteringar, bufferar og NVE-vêr for første 20-årsperiode er dokumenterte
i [DATA.md](DATA.md), med køyrerekkjefølgje og datafelt.

Første modellrunde er trena og evaluert. [MODEL.md](MODEL.md) viser
tidsdeling, referansemodellar, resultat, geografisk kontroll og avgrensingar.

For eiga læring: [Jupyter-notebooken](notebooks/skred_ml_laering.ipynb) går
gjennom innhenting, romleg beriking, kvalitetskontroll, variablar, trening,
kalibrering og evaluering. Kodecellene er køyrde og resultata lagra.
Vel prosjektet si `.venv` som Python-kjerne i VS Code eller Jupyter.
Standardkøyringa les eksisterande data og trenar ein liten demonstrasjon
i minnet. Full nedlasting og overskriving av modellresultat er av som standard.
Notebooken har installasjonskommandoar for Jupyter ved behov.

For berre dataarbeidet: [Vegnett og vegmeldingar](notebooks/vegnett_vegmeldingar_dataarbeid.ipynb)
går gjennom rådatahenting, segment og strekningsaggregering, Matplotlib-kart,
Xgeo-tekstfilter, historiske vegnummer, episodekandidatar og døgnsetikettar.
Alle 18 kodecellene er køyrde. Standardkøyringa bruker nedlasta rådata og
eksporterer eigne tabellar og kart under `data/notebook/vegnett_vegmeldingar/`.
`strekningar_med_vegmeldingar.csv` har éi rad per strekning med episodetal,
positive døgn og første/siste positive dato. Ein komplett strekning–døgnstabell
blir også laga for eit valt år (2018 som standard).
Kapittel 3b lagrar vegtabellane i `vegnett.sqlite` i same eksportmappe,
med primær-/framandnøklar, indeksar, uttaksmetadata og eit døme på SQL-spørjing.

NVE-aktsomheitskarta i det leverte zip-arkivet er kopla til veglinjene.
[AKTSOMHET.md](AKTSOMHET.md) dokumenterer kartlag, overlappsmål og kontroll
av kva strekningar og skred eit geografisk filter ville utelate.

[VEGMELDINGAR.md](VEGMELDINGAR.md) dokumenterer ei testa offentleg kjelde
til historiske Vegvesen-meldingar via NVE Xgeo, med årsdekning frå 2010,
eit lite prøveuttak og forslag til beriking utan dobbeltteljing av skred.

Heile det tilgjengelege Xgeo-uttaket til og med 3. oktober 2026 er no henta.
[VEGMELDINGAR_UTTAK.md](VEGMELDINGAR_UTTAK.md) forklarer tekstfilter,
vegkopling, episodekandidatar, årsdekning og tre alternative døgnetikettar.

## Omfang

Uttaket gjeld fylke 46 (Vestland), eksisterande europa-, riks- og fylkesvegar
(EV, RV, FV). Kommunale, private og skogsvegar er ikkje med i første uttak.
CSV-tabellane omfattar trafikantgruppe K på topologinivå Vegtrase.
Kryss og sideanlegg blir haldne utanfor, men ligg i rådata.
Armar og ulike delstrekningar er med og har eigne felt. Ferjestrekningar kan
vere med; `type_veg` må nyttast dersom ein vil avgrense til fysisk køyreveg.

## Filer

- `data/processed/strekningar.csv`: éi rad per fylke, vegkategori, fase,
  vegnummer og NVDB-strekning. Dette er utgangspunktet for ML-einingane.
- `data/processed/delstrekningar.csv`: éi rad per delstrekning, med meterintervall.
- `data/processed/vegsegment.csv`: detaljert kopling frå vegsegment til strekning,
  med meterreferansar, arm, retning, lenketype, vegtype, medium og WKT-geometri.
- `data/processed/kvalitetsrapport.json`: teljingar, lengder og ekskluderte segment.
- `data/raw/nvdb/`: originale API-sider og manifest med tidspunkt, filter og SHA256.

CSV er UTF-8 med BOM, komma som skiljeteikn og punktum som desimalskiljeteikn.
Bruk importfunksjonen i Excel dersom lokale innstillingar ventar semikolon.

`strekning_id`, til dømes `46_EV16_S1`, er koplingsnøkkelen mellom tabellane.
Vegkategori må vere med: same vegnummer kan finnast i fleire kategoriar.
NVDB-referansar kan endrast over tid; knyt alltid historiske data til eit
datert vegnettsuttak og kontroller omnummereringar.

## Lengde og geografi

Første uttak 4. oktober 2026 gav 43 600 segment, 1 211 delstrekningar og
957 strekningar: 83 på europaveg, 73 på riksveg og 801 på fylkesveg.
Summert segmentlengd er 7 250,779 km. Strekningslengdene varierer frå
3 meter til 50,587 km; dei er altså ikkje alle om lag 10 km.

Strekningane er NVDB sine administrative einingar, ikkje nykonstruerte
10-km-intervall. `lengde_m` er summen av NVDB-segmentlengdene i Vestland;
strekningar som kryssar fylkesgrensa er berre representerte med delen i fylket.
Armar og parallelle løp kan auke summen. `hovudlop_lengde_m` ekskluderer armar,
men kan framleis omfatte fleire parallelle løp. Dette er ikkje det same som
meterintervallet eller lengda av éin samanhengande trasé.

Meterverdiar høyrer til kvar delstrekning og skal ikkje summerast på tvers.
Geometrien er bevart med API-et sin `srid`; koordinatar er ikkje lengde/breiddegrad.
Bounding box er berre utstrekninga, og er ikkje eit representativt vêrpunkt.

## Køyring

Python 3.10 eller nyare, utan ekstra pakkar:

```powershell
python scripts/hent_nvdb.py
python scripts/hent_nvdb.py --offline
```

Første kommando hentar alle API-sider og lagar tabellar. Den andre byggjer
tabellane på nytt frå manifestet. Ein ufullført nedlasting avsluttar med feil;
CSV blir først bygd etter fullført uttak. Ikkje køyr fleire uttak samtidig.
Skriptet kontrollerer sidehashar, fylke/vegkategori/fase, duplikate segment,
unike strekningsnøklar og at lengdesummane stemmer.

## Neste steg: griddvêr og ML

Bruk linjegeometrien frå `vegsegment.csv` til å finne alle vêrceller som
vegen passerer, etter transformasjon til koordinatsystemet i det valde
NVE-produktet. Lag ei bru-tabell med `strekning_id`, `segment_id`,
`grid_id` og lengd av veg i cella. Verifiser griddefinisjon og koordinatsystem
mot API-et før kopling; desse er ikkje førehandsbestemte her.

Vêrdata bør lagrast separat med nøkkel `(grid_id, dato/tid)`. Då kan ein lage
lengdevekta middel, maksimum og variasjon per strekning og dato, framfor å
representere ein heil strekning med eitt midtpunkt. Bevar gjerne skiljet mellom
armar, hovudløp, ferjer og tunnelar i vidare analyse; tunneldekning må avklarast
med eigne NVDB-objekt og kan ikkje føresetjast frå vegtypen åleine.

Før trening treng me eit definert utfall, til dømes registrert skred på veg per
strekning og døgn, med kjelde, tidspunkt og skredtype. Vegnett åleine gir ikkje
skredfareetikettar. Del trening og evaluering både i tid og geografisk for å
unngå at nærliggande strekningar eller framtidsdata gir lekkasje.

## Kjelde

Statens vegvesen, NVDB API Les V4:
https://nvdb-docs.atlas.vegvesen.no/nvdbapil/v4/Vegnett/

Vegsystemreferansen:
https://www.nvdb.no/rammer-regelverk/referansesystem/vegsystemreferansen/

Historiske vegmeldingar er no kopla med dei offisielle reformlistene og geografisk kontroll. Sjå [HISTORISK_VEGKOPLING.md](HISTORISK_VEGKOPLING.md) for metode, før-/etter-tal og kontrollar.
