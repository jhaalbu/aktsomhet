# Xgeo-uttak og eit samla utfall for melde skred

Nedlastinga og dei tekniske kontrollane er fullførte. Det finst no eit
separat kandidatgrunnlag for eit binært utfall **meldt skred/nedfall på
strekning og dato**, utan krav om korrekt skredtype. NVDB-etikettane er
bevarte. Ingen ny skredmodell er trena i denne runden.

## Uttaket

Kjelde: [NVE XgeoVeimelding2, lag 13](https://gis3.nve.no/map/rest/services/Mapservices/XgeoVeimelding2/MapServer/13),
med vegmeldingar frå Statens vegvesen. Me lasta ned nasjonalt for å unngå
at eit tekstfilter på Vestland mistar eldre fylkesnamn eller meldingar
utan fylkesnamn. Uttaket inneheld **105 407 postar**, med meldingsdatoar
til og med 3. oktober 2026. Det er 30 færre enn undersøkinga som også
tok med 4. oktober. Åra 2006–2009 gav null postar; første år med postar
er 2010. Ingen full 20-årsdekning er stadfesta.

`hent_xgeo_vegmeldingar.py` hentar opptil 1 000 postar per side, årsvis,
med sortering på dato, post-ID, versjon og meldingsnummer. Det kontrollerer
duplikate rader og teljingar før/etter kvart år, og bevarer råsvar, førespurnad
og SHA256. Fullførte årsuttak kan brukast om att. Metadata- og JSON-feil
blir ikkje tolka som tomme sider. Uttaket er ein kopi av det tenesta tilbyr
no, ikkje stadfesting av at alle originale versjonar eller sletta meldingar
er med. Like teljingar før/etter er heller ikkje garanti for eit atomisk
uttak frå ei levande teneste.

Rådata: `data/raw/xgeo_vegmeldingar/`, komprimerte JSON-sider og manifest.

## Filtreringa

Det er **23 177 geografiske kandidatpostar**: visingspunkt innan 1 km
frå vegnettet vårt eller stadnamn med Vestland/Hordaland/Sogn og Fjordane.
Dette er eit søkeutval, ikkje ei fylkesavgrensing med polygon. Koplingane
til ML-einingar blir deretter avgrensa til dei 957 eksisterande strekningane.

### Tekstreglar

| Klasse | Kandidatpostar | Bruk |
|---|---:|---|
| Meldt skred/nedfall | 8 948 | Kandidatar til utfallet |
| Skredfare | 1 487 | Separat; ikkje faktiske skred |
| Opning etter skred | 200 | Stadfestar omtale, men ikkje dato for skredet |
| Kontrollert skred | 17 | Separat; ikkje naturleg utløyst skred |
| Uavklart | 2 | Usikker eller nekta skredomtale |
| Anna | 12 523 | Ingen eksplisitt omtale av faktisk skred i teksten |

Me leitar etter eksplisitte ord for ras/skred, steinsprang og nedfall i
meldingsteksten. Rasfare blir fjerna frå vurderinga lokalt, slik at ei
melding om både eit snøras og vidare rasfare framleis kan vere positiv.
Samansette synonym som «steinskred/steinsprang» blir handterte saman.
Usikkert sluttidspunkt for ei stenging blir ikkje forveksla med usikkert
skred. Kategori åleine er ikkje nok: eldre postar kategoriserte som
`skred` kan vere reine føremeldingar.

Isnedfall er med i dette breie utfallet, slik det også inngår i den første
NVDB-modellen. Vanleg flaum utan skred, uvêr og kontrollert utløsning er
ikkje med. Råkategori og tekst er bevarte, sjølv om ML-utfallet er samla.

Dette er regelbaserte kandidatklassar, ikkje manuelt verifiserte fasitsvar.
`anna` kan også innehalde skred som reglane ikkje greier å kjenne att.

### Vegkopling

Kandidatkjelda gir visingspunkt og nokre start-/sluttpunkt, ikkje
nødvendigvis den eksakte skredstaden. Me brukar dagens veggeometri,
EPSG:25833 etter transformasjon frå EPSG:4326.

Det strenge utvalet krev:

1. Same vegkategori, og dagens vegnummer eller eit dokumentert historisk nummer frå reformlistene. Gammalt fylke blir kontrollert mot kommunen på veggeometrien. Gamle alias er tillatne til og med 2021; seinare bruk blir ikkje automatisk omsett.
2. Visingspunkt innan 100 meter frå veglinja.
3. Minst 20 meter større avstand til nest næraste strekning blant tillatne noverande og historiske nummer,
   dersom det finst fleire kandidatar.
4. Eventuelle start-/sluttpunkt må også liggje innan 100 meter frå den
   valde strekninga. Lange eller grove vegmeldingsstrekningar blir bevarte
   som usikre kandidatar, og ikkje gjorde til skred på alle vegane langs dei.

100/20 meter er forsøksgrenser, ikkje verifisert stadnøyaktigheit.
19 077 kandidatpostar får ei vegkopling; 1 802 av desse har grov utstrekning.
Reformnummer frå Hordaland og Sogn og Fjordane er no omsette med geografisk kontroll. Flytta vegar, kategoriendringar og omnummereringar utanfor listene kan framleis gi manglande kopling.
Me tvingar ikkje ei melding til næraste veg med feil vegnummer.

### Tid og oppdateringar

UTC-variantane av tidsfelta blir normaliserte frå både millisekund og
ISO-strengar, og omrekna til lokal dato i Europe/Oslo.
Ein etikettdato er **gyldigheitsstarten i den første positive, kopla
meldinga i ein episodekandidat**, ikkje verifisert fysisk skredtid.
Opprettings- eller versjonstid blir bevart for vidare kontroll.
Meldingar utan brukbart UTC-felt blir ikkje positive i det strenge utvalet.

Same situasjons-ID og strekning blir samla til episodekandidatar. Eit
opphald over sju døgn mellom positive meldingsdatoar startar ein ny
episodekandidat. Dette er ei dokumentert heuristikk, ikkje sikker
identifikasjon av uavhengige skred. To skred innan same situasjon kan bli
slått saman, og ei lang stenging kan bli delt. Positivt første tidspunkt
som ikkje oppfyller radreglane blir ikkje flytta fram til ei seinare,
reint kopla oppdatering innan den same kopla episodekandidaten.

## Resultat: kandidatetikettar i 2013–2026

Det strenge utvalet omfattar **7 191 meldingar**, samla til **4 787
episodekandidatar**, på 562 strekningar. Fleire kandidatar på same dato
gir éin binær positiv. Dette gir **4 522 positive strekning–døgn**.

| Kjeldesamanlikning på same strekning og dato | Positive døgn |
|---|---:|
| Berre Xgeo-kandidatar | 3 388 |
| Begge kjelder | 1 134 |
| Berre NVDB 445 | 9 240 |
| Xgeo totalt | 4 522 |
| NVDB totalt | 10 374 |
| Minst éi kjelde | 13 762 |

«Berre Xgeo» betyr ikkje 3 388 stadfesta nye skred. Dei kan vere nye
registreringar, feilkoplingar, skred frå ein annan dato eller feil i
tekstreglane. «Begge» er heller ikkje stadfesting av identiske hendingar.
Samanlikninga er mellom binære døgn, ikkje ei ferdig deduplisering av
hendingar på tvers av kjelder.

### Tydeleg endring over tid

| Periode | Xgeo-positive døgn | NVDB-positive døgn |
|---|---:|---:|
| 2013–2020 | 599 | 5 221 |
| 2021–2022 | 702 | 1 736 |
| 2023 | 849 | 916 |
| 2024–3. oktober 2026 | 2 372 | 2 501 |

Det låge utvalet tidleg og den seinare auken må undersøkast. Årsrapporten
`filtersteg_per_ar.csv` viser tap i tekst- og vegkoplingstrinna, medan
`kjeldesamanlikning_per_ar.csv` viser dei endelege binære døgnutfalla.
Den historiske nummerrettinga auka 2013–2020 frå 311 til 599 positive døgn. Kjeldepraksis og andre historiske endringar kan framleis påverke utviklinga.
Desse tala må ikkje tolkast direkte som utvikling i faktisk skredfrekvens.

## Bør me berre bruke vegmeldingar, utan skredtype?

Eitt samla utfall er ei rimeleg første avgrensing når typeklassifiseringa
er usikker. **Den første modellen vår brukte allereie alle NVDB-skredtypar
samla.** Me får derfor ikkje ein slik gevinst berre ved å fjerne skredtype
frå modellen. Samla etikettar blandar også prosessar med ulik reaksjon på vêr.

Eg tilrår å bevare tre alternative utfall:

- `registrert_skred`: dagens NVDB-utfall.
- `vegmelding_skred`: strengt kandidatutfall frå Xgeo, utan skredtype.
- `skred_ei_av_kjeldene`: binær union, framleis eit kandidatutfall.

Dei ligg i separate, årlege etikettfiler som kan koplast ein-til-ein til
vêrgrunnlaget. Originaldata blir ikkje overskrivne. Ein null i Xgeo betyr
ingen behalden melding, ikkje dokumentert skredfråvær eller komplett
overvaking. Lågare tal før 2021 gjer eit direkte kjeldeskifte i den
eksisterande tidsdelinga særleg vanskeleg å forsvare.

Om målet blir trafikantrelevante *melde skred* framfor alle registrerte
skred, kan Xgeo vere eit eige utfall. Me må først kontrollere tekst,
lokalisering og datoar og vurdere ein meir stabil periode. Betre ML-resultat
er ikkje demonstrert, og samanlikning av måltal mellom ulike utfall er
ikkje ei rettferdig samanlikning av skredprediksjonsevne i seg sjølv.
Etter-hendingsmeldingar skal heller ikkje bli prediktorar for same skred.

## Kontroll og filer

`manuell_kontroll.csv` har **586** eksempel, stratifiserte på år, klasse
og radreglane, med tomme `review_label` og `review_comment`. Fyll dei ut
i ei kopi. Kontroller også eit utval av utelatne meldingar, ikkje berre
dei positive. Dette utvalet er ikkje eit tilfeldig estimat av samla
presisjon utan vekting etter stratumstorleik.

Alle tekniske kontrollar gjekk gjennom: råhashar og teljingar, 12
grensetilfelle for tekstreglane, episode-/datokopling, romlege reglar og
uavhengige døgnsummar. Dette stadfestar ikkje semantisk nøyaktigheit.

Alt behandla ligg i `data/processed/vegmeldingar/`:

- `meldingar_vestland_kandidatar.csv/.parquet`: originalfelt og filtergrunnlag.
- `skredepisodar_kandidatar.csv/.parquet`: kopla, positive episodekandidatar.
- `skredepisodar_strengt_utval.csv`: første strenge analyseutval.
- `vegmelding_skred_dogn.parquet`: positive Xgeo-døgn.
- `positive_dogn_kjeldesamanlikning.csv/.parquet`: positive døgn frå minst éi kjelde.
- `etikettar_dogn/<år>.parquet`: komplett eksisterande veg/døgnpanel med tre
  alternative utfall. Ingen kontrollert negativ fasit er implisert.
- `filterrapport.json`, `validation_report.json`, årsrapportane og kontrollutvalet.

```powershell
.venv/Scripts/python.exe scripts/hent_xgeo_vegmeldingar.py
.venv/Scripts/python.exe scripts/hent_xgeo_vegmeldingar.py --offline
.venv/Scripts/python.exe scripts/filtrer_xgeo_vegmeldingar.py
.venv/Scripts/python.exe scripts/valider_vegmeldingar.py
```

Notebooken har fått eit eige kapittel med etikettkopling og kjeldesamanlikning.
Alle 17 kodeceller er køyrde utan feil. Vidare trening mot desse kandidatane
bør vente til kvalitetskontrollen og val av føremål/periode er gjort.
