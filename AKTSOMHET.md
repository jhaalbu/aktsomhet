# Aktsomheitskart og vegstrekningar

Brukaren leverte `data/raw/nve/NVE_47551B14_1791106303286_10540.zip`, eit
NVE-uttak med GeoJSON for Vestland datert 4. oktober 2026. Arkivet er bevart.
`scripts/kople_aktsomhet.py` les kartlaga direkte frå zip med strøymande JSON.

## Kartlag i første kopling

- Jord- og flaumskred: `Skred_JordFlomAktsomhetOmr`, det samla laget.
  Deldatasetta blir ikkje lagde til på nytt.
- Steinsprang: både `Skred_SteinsprangAktsomhet_UtlopOmr` og
  `Skred_SteinsprangAktsomhet_UtlosningOmr`.
- Snøskred: `Skred_SnoAktsomhet_S2`, utan skogeffekt. Variantane S3 og
  S2 med skogeffekt er bevarte i arkivet og kan undersøkjast separat.

S2/S3 er namn på variantar for arealplanlegging, ikkje risikoklassar for vegar.
Losneområde, skoglaget og indekskartet for snø blir ikkje blanda inn i
aktsomheitslaget som eigne skredutløpsområde i denne første koplinga.

## Resultat frå koplinga

Alle 957 vegstrekningane er med i output. Direkte treff per tema:
669 for steinsprang, 794 for jord-/flaumskred og 770 for snøskred.
Desse tala overlappar og skal ikkje summerast.

| Filter | Strekningar behaldne | Strekningar utelatne | Hendingar på utelatne strekningar, 20 år | Positive strekning–døgn utelatne |
|---|---:|---:|---:|---:|
| Direkte treff | 837 | 120 | 105 | 94 av 13 595 |
| Område innan 20 m | 869 | 88 | 40 | 37 av 13 595 |

Direkte filter utelèt 434,1 km geometrisk union-lengd. Av dei 105 hendingane
er 98 registrerte som Stein, 6 som Jord/løsmasse og 1 som Flomskred.
104 av hendingane har berre kopling til utelatne strekningar; éi har også
ei kopling til ei behalden strekning. Ukopla NVDB-hendingar er ikkje med
i denne filterkontrollen.

På den eksisterande sluttesten ville direkte filter utelate 22 av 2 501
positive strekning–døgn, medan 20 m-regelen ville utelate 10. Desse tala
er konsekvensrapportering, ikkje dokumentasjon på betre modellresultat.

Alle kontrollane i `validation_report.json` gjekk gjennom: komplette nøklar,
CSV/Parquet-samsvar, andelar og union-grenser, og uavhengig rekna filterteljingar.
Notebooken er oppdatert og alle 16 kodecellene er køyrde utan feil.

## Metode

GeoJSON-filene har eksplisitt EPSG:25833; koordinatane er ikkje grader.
Veglinjer blir strippa for Z og transformerte frå NVDB sitt horisontale CRS.
Segment per strekning blir samla med geometrisk union, med armar og parallelle
løp slik dei finst i det eksisterande uttaket. Tunnelar og ferjer er ikkje
skilde ut. Ugyldige polygon blir reparerte med `make_valid` og talet rapportert.

Me finn polygon som kryssar veglinjene med romleg indeks. For kvar strekning
blir kandidatpolygon slått saman før linja blir kryssa med unionen.
Dermed blir overlappande aktsomheitspolygon ikkje dobbelttelte.
Andelen er overlappslengd delt på geometrisk veglengd, som kan avvike frå
summen av NVDB sine segmentlengdfelt. Alle andelar blir kontrollerte til 0–1.

`behald_direkte` er sann ved minst eitt geometrisk treff, også eit reint
punkt-/grensetreff. `behald_innan20m` er ei alternativ sensitivitetsregel:
minst eitt område innan 20 meter frå veglinja. 20 meter er vårt forsøksval,
ikkje ein dokumentert posisjonsnøyaktigheit eller ei ny faregrense.
Ingen av reglane brukar vêrbufferen på 2 km.

## Output

Alt ligg i `data/processed/aktsomhet/`:

- `strekning_aktsomhet.csv` og `.parquet`: éi rad per strekning, med meter,
  andel og treff per tema, union for alle tema og to filtervariantar.
- `strekningar_utan_direkte_treff.csv`: strekningar eit direkte filter ville fjerne.
- `skred_pa_strekningar_utan_treff.csv`: unike hending–strekning-koplingar
  som ville falle utanfor. Ei hending kan finnast på fleire strekningar.
- `skredtype_filterkontroll.csv`: teljingar etter type og om strekninga er behalden.
- `rapport.json`: kartlag, CRS, polygonkontrollar, SHA256 og konsekvensar
  for heile perioden, modelltreninga og den eksisterande sluttesten.

`unique_events_on_removed_sections` tel hendingar med minst éi utelaten
strekning. `events_only_on_removed_sections` tel berre hendingar utan nokon
behalden strekning. `positive_section_days_removed` er tapte positive
strekning–døgn, det same utfallet som modellen skal predikere.

Koplinga endrar ikkje dei originale veg-, skred-, vêr- eller modellfilene.
Notebooken har eit eige kapittel som les desse tabellane.

## Tolking og vidare forsøk

Dette er ein kontroll av eit mogleg filter, ikkje dokumentert betre ML-resultat.
Skred på ei behalden strekning er ikkje nødvendigvis inne i eit polygon:
her kontrollerer me strekningsutvalet, ikkje punktlokalisering av kvar hending.
Null overlapp betyr heller ikkje dokumentert fråvær av skredfare.
Kartlaga dekkjer ikkje alle skredtypane i NVDB-utfallet.

Kartuttaket er noverande og kan byggje på opplysningar frå seinare tidspunkt
enn historiske måldatoar. Det er ikkje eit historisk tilgjengeleg kartgrunnlag.
Testetikettane er brukte til å rapportere filterkonsekvensar; tilpassing av
filteret etter desse tala vil gjere testen til utviklingsdata.

Neste modellforsøk bør samanlikne aktsomheitsandelar som variablar med eit
fast, førehandsdefinert filter, og rapportere tapte skred på heile vegnettet.

```powershell
.venv/Scripts/python.exe scripts/kople_aktsomhet.py
.venv/Scripts/python.exe scripts/valider_aktsomhet.py
```

Kjelde: NVE og underliggjande kartprodusentar. Produktark og eigenskaps-
beskrivingar ligg i det leverte arkivet saman med bruksvilkåra.
