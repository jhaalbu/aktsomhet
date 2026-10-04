# Historiske vegmeldingar som supplement til NVDB-skred

Undersøkt 4. oktober 2026. **Ei offentleg historisk kjelde er funnen og
testa:** NVE si Xgeo-kartteneste har vegmeldingar frå Statens vegvesen,
med lesbare historiske postar. Dette er ikkje det same som eit komplett
arkiv over alle trafikkmeldingar eller eit kvalitetssikra skredregister.
Ingen meldingar er lagde til modellutfallet enno.

## Konkret funn: XgeoVeimelding2

[NVE-tenesta](https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer/13)
har eit samla lag `veimeldinger` (13), i tillegg til temalag for skred,
rasfare, flaum, isnedfall, uvêr og snøskredkontroll. Lag 13 samlar dermed
fleire naturfare-/vêrtema; namnet er ikkje dokumentasjon på alle vegmeldingar.

Direkte API-kontroll gav **105 437 postar nasjonalt**. Sortert spørring på
`FROM_DATE` gav 27. november 2010 som første dato og 4. oktober 2026 som
siste. Lag 5, snøskred, hadde 6 378 postar nasjonalt. Første dato der var
13. januar 2011, og den siste 24. mai 2026. Sistnemnde post var avslutta
28. mai, så kjelda inneheld avslutta meldingar, ikkje berre aktive meldingar.

Årstala under gjeld meldingspostar, ikkje unike skred eller situasjonar:

| År | Nasjonale postar i lag 13 |
|---|---:|
| 2006–2009 | 0 |
| 2010 | 1 |
| 2011 | 2 195 |
| 2012 | 3 319 |
| 2013 | 5 395 |
| 2014 | 3 941 |
| 2015 | 5 269 |
| 2016 | 2 848 |
| 2017 | 4 820 |
| 2018 | 4 205 |
| 2019 | 4 106 |
| 2020 | 6 991 |
| 2021 | 3 384 |
| 2022 | 7 350 |
| 2023 | 11 142 |
| 2024 | 12 823 |
| 2025 | 19 359 |
| 2026, til kontrolltidspunktet | 8 289 |

Summen av årsuttaka stemmer med totalteljinga. Teljingane stadfestar at
postar finst i desse åra, **ikkje** at kvar dag, veg eller hendingskategori
har full dekning. Auken i posttal kan også skuldast kjelde-/systemendringar.
Den etterspurde perioden 2006–2026 er altså ikkje dekt fullt ut her.

### Prøveuttak i prosjektet

50 postar frå 2015 er lagra i
`data/raw/vegmeldingar_research/sample_west_2015.csv` og original JSON ved sida.
Prøven er vald med stadnamn som inneheld Hordaland, Sogn og Fjordane eller
Vestland. Dette er eit illustrerande tekstutval, ikkje eit komplett geografisk
Vestland-uttak. Historiske fylkesnamn og vegar over fylkesgrensene må handterast.

Prøven inneheld mellom anna meldingar om snøras og rasfare på Tyin–Årdal,
men også gjentekne uvêrs-/stengingsmeldingar på Hol–Aurland. Nokre postar med
`CATEGORY=skred` er føremeldingar utan ei omtalt skredhending.
Det er derfor nødvendig å tolke tekst og metadata saman.

Tilgjengelege felt omfattar:

- `EXT_SIT_NO`, `EXT_REC_NO`, `VERSION_NO`: situasjon, post og versjon.
- `MSG_DESCRIPTION`, `FREE_TEXT`, `CATEGORY`, `PROB_CATEGORY`, `MESSAGE_TYPE`.
- `FROM_DATE_UTC`, `TO_DATE_UTC`, opprettings- og versjonsdato med UTC-variantar.
- `ROAD_TYPE`, `ROAD_NUMBER`, `NAME` og start-/slutt-/visingskoordinatar.
- Punktgeometri i EPSG:4326; punktet kan representere ei lang strekning.

Eldre svar brukar millisekund frå epoch, nyare svar brukar også ISO-datostrengar.
`FROM_DATE` og `FROM_DATE_UTC` kan ha ulike klokkeslett. Normalisering må
ta utgangspunkt i dokumenterte UTC-felt og lokal dato i Europe/Oslo, med
kontroll av faktisk tidsmeining. Verken opprettingsdato eller stengingsstart
er automatisk tidspunktet eit skred skjedde.

API-et svarar med HTTP 200 også ved ein JSON-feil. Vanlege statistikkspørringar
feila, men `returnCountOnly` og sorterte vanlege spørringar fungerte.
Paginering krev `orderByFields`, sidan tenesta ikkje har vanleg OID-felt.
Maksimal sidestorleik er 1 000. Full nedlasting må kontrollere stabil sortering,
duplikatar og fullstende, og må ikkje rekne ein feil som ei tom side.

## Andre spor hos Statens vegvesen

### DATEX og den opne kartflata

[Vegvesenet si DATEX-side](https://www.vegvesen.no/fag/teknologi/apne-data/et-utvalg-apne-data/hva-er-datex/)
beskriv den ordinære publikasjonen som pågåande og planlagde forhold.
Ho krev registrering. Me fann ikkje eit dokumentert historisk 20-årsendepunkt
i denne publikasjonen. Registrering åleine stadfestar ikkje tilgang til eit arkiv.

Den offentlege OGC-kartflata `datex_3_1:SituationSimple` gav eit gyldig
GeoJSON-prøvesvar utan registrering. Ho har mellom anna situasjons-ID,
versjon, tekst, tidspunkt og geometri, men historisk fullstende er ikkje
stadfesta. Dette er eit mogleg spor for løpande innsamling frå no av.

### Vegloggen/HBT i Saga

[Saga-introduksjonen](https://docs.saga1.vegvesen.no/intro/) nemner eksplisitt
Vegloggen/HBT som kjelde til standardiserte analysedata i BigQuery.
[SQL-dokumentasjonen](https://docs.saga1.vegvesen.no/bruke-saga/analyse-i-bigquery/nyttig-sql-kunnskap/)
har eit konkret døme med tabellen `saga-veglogg-prod-wznf.internal.situations_v2`.
Dette er dokumentasjon på eit analysedatasett, ikkje på ope tilgjenge eller
at tabellnamnet framleis er gjeldande. Årsdekning og eksternt uttak må avklarast.

[Vegvesenet sin skredsikringsrapport](https://www.vegvesen.no/contentassets/82b0e6022a914be0aee1386507bd8628/skredsikringsbehov-riks-og-fylkesvegar-i-midt.pdf)
omtalar mangelfulle NVDB-skredregistreringar og Vegloggen/Xgeo som supplerande
grunnlag. Det støttar relevansen av sporet, men dokumenterer ikkje graden
av underrapportering i vårt Vestland-datasett.

## Tilrådd beriking

1. Hent Xgeo-historikken i små sider og bevar råsvar og tidspunkt.
   Avgrens geografisk med dokumentert fylkesgeometri, ikkje berre fylkesnamn.
2. Samle oppdateringar av same situasjon/post og skil mellom ny hending,
   oppdatering, opning og retting. Ei stenging over fleire døgn er ikkje fleire skred.
3. Lag separate klassar for meldt skred, skredfare/førebyggjande stenging,
   kontrollert snøskred og vanleg flaum/uvêr. Flom utan skred er eit anna utfall.
4. Kople via vegkategori/-nummer og geometri. Bruk historiske vegreferansar
   der dei finst. Ikkje spre eit visingspunkt eller ei generell stenging
   til alle nærliggande strekningar utan å vurdere kva veg meldinga gjeld.
5. Finn sannsynlege samsvar med NVDB 445 i tid og rom. Bevar kjeldeflagg og
   koplingsusikkerheit; ikkje tel same skred to gonger.
6. Evaluer eit utvida utfall separat frå det opphavlege NVDB-utfallet.
   Meldingar publiserte etter skredet skal ikkje brukast som førehandsvariablar.

Det naturlege første analyseutvalet er 2013–2026, sidan vinddata og modellen
allereie byrjar i 2013. Kjeldefullstende må likevel undersøkjast per år.

## Utkast til førespurnad om betre historikk — ikkje sendt

Kontaktpunktet for DATEX er `datex@vegvesen.no`, publisert i
[Vegvesenet sin dataportal](https://dataut.vegvesen.no/dataservice/datex).
Be dei eventuelt vise førespurnaden vidare til Vegloggen/HBT/Saga eller VTS.

> Me arbeider med eit lærings-/analyseprosjekt om registrerte skred langs
> E-, R- og F-vegar i dagens Vestland. Me ønskjer maskinlesbare historiske
> vegmeldingar for 4. oktober 2006–3. oktober 2026, eventuelt frå tidlegaste
> tilgjengelege dato. Kan de tilby eit uttak frå Vegloggen/HBT/Saga med
> publisert meldingstekst, hendingsklassar, situasjons-/post-ID og versjonar,
> hendingstid, publiseringstid, gyldigheit, geometri og vegreferansar?
> Me ønskjer også opplysningar om årsdekning, arkiveringspraksis og
> systemendringar, og om Xgeo-kopien har avgrensingar eller manglande periodar.
> Stadfest gjerne lisens og om eit uttak utan person-/interne fritekstdata
> kan leverast som CSV, Parquet eller GeoJSON.

## Reproduserbar kontroll

`scripts/undersok_vegmeldingar.py` kontrollerer tenester, felt og første/siste
post. `scripts/prove_historiske_vegmeldingar.py` kontrollerer årstal og prøven.
Råsvar og førespurnadsmanifest ligg i `data/raw/vegmeldingar_research/`.
Denne undersøkinga har ikkje endra etikettar eller trent modellar på nytt.
