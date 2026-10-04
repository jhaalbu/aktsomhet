# Første modellrunde: registrerte skred langs veg i Vestland

Treninga er fullført og dei lagra modellane er kontrollerte. Den første
modellen gir **ikkje dokumentert gevinst over historisk skredfrekvens når
me flaggar ti strekningar kvar dag**. Vêr og veg vart valt på valideringsdata,
men fann 174 av 2 501 positive strekning–døgn i sluttesten; referansen fann 176.

## Mål og datadeling

Målet er minst eitt **registrert** NVDB-skred på ei strekning på ein dato.
Alle skredtypar er med i denne første runden. Det er ikkje talet på
uavhengige skredhendingar: same hending kan treffe fleire strekningar.
Null betyr ingen hending registrert i uttaket.

Vind har gyldige verdiar frå 2013. Modellen er derfor trena på perioden
2013–2026; 2012 blir berre brukt som historikk til å byggje lagga variablar
ved starten av 2013.

| Del | Periode | Strekning–døgn | Positive døgn |
|---|---|---:|---:|
| Trening | 2013–2020 | 2 796 354 | 5 221 |
| Modellval og tidleg stopp | 2021–2022 | 698 610 | 1 736 |
| Sannsynskalibrering | 2023 | 349 305 | 916 |
| Sluttest | 2024-01-01–2026-10-03 | 963 699 | 2 501 |

Alle 957 strekningar på same dato er i same tidsdel. Ingen negativ
undersampling, oversampling eller klassevekting er brukt. Valideringsdata
styrer tidleg stopp, og modellen er vald etter recall blant ti daglege
flagg. Sluttesten er ikkje brukt til å endre modellinnstillingane.

## Modellane

1. **Historisk frekvens:** glatta registrert skredfrekvens per strekning og
   månad, rekna berre frå 2013–2020. Globale månadsratar og strekningsratar
   blir brukte som priorar. Glattinga bruker 365 døgn for strekningsraten
   og 60 døgn for strekning–månad. Utan kjend strekning blir regional
   månadsfrekvens brukt som fallback.
2. **Vêr og årstid:** LightGBM med lagga vêrvariablar og sesong.
3. **Vêr og veg:** same vêrvariablar, pluss lengd, armandel, vegkategori
   og strekning som kategorisk variabel.

Vêrvariablane omfattar førre dags middel og utvalde maksimum, tre- og
sju-døgnssummar av nedbør og nysnødjupn, temperatur- og snødjupnendring,
vindretning som sinus/cosinus, vindhastigheit, jordmetning og lagga
datodekning. Ingen vêrverdiar frå sjølve måldatoen er brukte. Ingen skredtal,
skredtypar eller skredteljingar frå heile 20-årsperioden inngår som prediktorar.

LightGBM handterer manglande verdiar direkte. Innstillingane vart bestemte
før sluttesten: 31 blad, læringsrate 0,05, minst 400 observasjonar per blad,
L2-regularisering 5, maksimalt 600 tre og tidleg stopp etter 50 rundar utan
betre average precision. Tilfeldig frø er 20261004 og treninga bruker åtte
CPU-trådar. Vêr og veg stoppa ved åtte tre; vêrmodellen hadde fleire tre.

Ein sigmoid på logit av råskåren blir tilpassa med 2023-data for kvar modell.
Validering 2021–2022 blir evaluert med råskår, utan kalibrering frå framtida.
Sluttesten bruker kalibreringa frå 2023. Dei rapporterte skårane er ikkje
verifiserte sannsyn for alle faktiske skred, berre for registermålet.

## Resultat på sluttesten

Perioden har 1 007 døgn. Ti flagg per dag gir 10 070 flagga strekning–døgn.
Ved like skårar blir dei same faste, tilfeldig ordna strekningsplassane
brukte for alle modellar, så alfabetisk orden ikkje avgjer samanlikninga.

| Modell | Average precision | Skred-døgn funne ved topp 10 | Treff blant flagga døgn |
|---|---:|---:|---:|
| Historisk frekvens | 0,00975 | 176 / 2 501 = 7,04 % | 1,75 % |
| Vêr og årstid | 0,01160 | 162 / 2 501 = 6,48 % | 1,61 % |
| Vêr og veg | 0,01248 | 174 / 2 501 = 6,96 % | 1,73 % |

Grunnfrekvensen i sluttesten er 0,2595 %. Modellen med vêr og veg har betre
average precision enn referansen, men ikkje betre resultat ved ti daglege
flagg. Desse måla vurderer ulike sider av rangeringa. Ved 50 flagg per dag
finn vêr og veg 561 positive døgn, mot 538 for referansen, men fleire flagg
aukar også talet på døgn utan registrert hending som blir flagga.

Ein para bootstrap med 1 000 trekningar av kalender-månadsblokker gir
95 %-intervall for endringa i recall ved topp 10 på **−0,92 til +0,69
prosentpoeng** for vêr og veg mot referansen. Intervallet støttar ikkje
ein sikker gevinst. Det gjeld faste, ferdigtrena modellar og omfattar
ikkje usikkerheit ved ny trening eller registreringsskeivskap.

![Modellsamanlikning](models/first_run/temporal/evaluation.png)

## Geografisk kontroll

Ein separat modell vart trena utan 89 nordlege strekningar. Valet vart
gjort frå koordinatar, utan å sjå på testetikettane: heile strekninga måtte
ha `ymin >= 6 880 000` i UTM33. Treningsområdet inneheld 849 strekningar med
`ymax < 6 876 000`; 19 grense-strekningar er utelatne. Avstanden på minst
4 km mellom strekningsboksane unngår overlapp mellom 2 km-bufferane.
Trening, modellval og kalibrering bruker berre treningsområdet. Testen
bruker både eit nytt geografisk område og framtidige datoar frå 2024.

I dette området er 257 strekning–døgn positive. Den geografiske modellen
med vêr og veg finn 48 ved ti flagg per dag, mot 23 for frekvensreferansen.
Dette er 18,68 % mot 8,95 %. Referansen kjenner ikkje dei nye strekningane
og må bruke fallback. Månad-bootstrapen gir ei endring på +4,64 til
+15,30 prosentpoeng. Dette er ein førebels indikasjon på overførbar
informasjon, men berre eitt geografisk område er testa.

Topp 10 av 89 strekningar er eit langt større utval enn topp 10 av 957;
dei geografiske recall-tala skal derfor ikkje samanliknast direkte med
recall-tala for heile fylket. Ukjende strekningskodar blir handterte av
LightGBM sine vanlege kategoriske prediksjonsreglar; dei har ingen
treningsobservasjonar i den geografiske modellen.

## Tolking og neste eksperiment

Strekningsidentiteten står for om lag 83 % av den rapporterte split-gain
i modellen med vêr og veg. Gain er ei modellbeskriving, ikkje eit kausalt
mål, og kategoriske variablar kan påverke denne fordelinga. Likevel viser
resultatet at denne første modellen i stor grad bygger på kvar hendingar
historisk har vore registrerte.

Neste førehandsdefinerte modellrunde bør skilje mellom steinsprang,
snøskred og jord-/flom-/sørpeskred, og ta inn terrenghelling, høgd,
tunnelar og skredsikring. Den eksisterande sluttesten er no brukt til
rapportering; mykje vidare tuning mot desse resultata vil gjere han til
utviklingsdata. Nye innstillingar bør styrast av tidsvalidering før nye
resultat på seinare eller andre førehandsdefinerte område blir undersøkte.

Meteorologiske døgn og faktisk datatilgjenge på varslingstidspunkt er
ikkje avklarte. Dette er ei retrospektiv modelløving med kalenderlaggar.
Vegnettet og NVDB-referansane er frå dagens uttak, ikkje rekonstruerte
historiske vegar. Registreringspraksis og hendingar utan kopling kan også
påverke modellen.

## Filer og køyring

- `scripts/tren_modell.py`: datadeling, variablar, referansemodellar,
  trening, kalibrering, prediksjonar, evaluering og månad-bootstrap.
- `scripts/valider_modell.py`: uavhengige kontrollar av dei lagra resultata.
- `models/first_run/temporal/`: dei tre modellane sine resultat og prediksjonar.
- `models/first_run/geographic/`: geografisk kontroll og strekningsutval.
- `*.txt`: lagra LightGBM-modellar; `*_calibration.json`: kalibreringsparameterar.
- `*_metadata.json`: variablar, innstillingar og valt tal tre.
- `*_test_predictions.parquet`: alle sluttestprediksjonar med etikettar.
- `*_test_top10.csv`: ti høgast rangerte strekningar per dato.
- `metrics.csv`, `metrics.json`, `bootstrap.json`: måltal og intervall.
- `data_audit.json`: datadeling, variablar og SHA256 for kjeldefilene.
- `validation_report.json`: kontrollresultata. Alle kontrollane gjekk gjennom.

```powershell
.venv/Scripts/python.exe scripts/tren_modell.py
.venv/Scripts/python.exe scripts/valider_modell.py
```

Treningskommandoen skriv over første modellrunde. Kopier eksisterande
resultat før ein køyrer eit nytt eksperiment i same mappe. Bibliotekversjonar
er feste i `requirements.txt`.

Dokumentasjon for bibliotek:
https://lightgbm.readthedocs.io/en/stable/Advanced-Topics.html
https://lightgbm.readthedocs.io/en/stable/Python-API.html
https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html
