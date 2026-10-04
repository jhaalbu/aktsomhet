# Historiske vegnummer og tap av vegmeldingar

Undersøkt 4. oktober 2026. Dette er den opphavlege diagnosen før retting. Rettinga er no gjennomført; sjå [HISTORISK_VEGKOPLING.md](HISTORISK_VEGKOPLING.md).

## Noverande kopling

`scripts/filtrer_xgeo_vegmeldingar.py` brukar koordinat, men krev samtidig lik vegkategori og vegnummer som i det noverande NVDB-vegnettet. Næraste strekning må vere innan 100 meter, og avstandsskilnaden til neste kandidat må vere minst 20 meter. Oppgitte start-/endepunkt meir enn 100 meter frå strekninga gir grov stadfesting og utelating frå strengt utval. Historiske nummer og hovudparsellar blir ikkje omsette. Dette kan miste ei melding på gammal Fv241 sjølv om punktet ligg på dagens Fv5623.

## Diagnostisk samanlikning

`scripts/diagnose_vegnummer.py` fjernar berre kravet om likt vegnummer, og beheld vegkategori, 100-metersgrensa og tvitydigheitsgrensa. Resultata ligg i `data/processed/vegmeldingar/vegnummer_diagnose/`.

| Periode | Meldingsrader med eksplisitt skred | Opphavleg kopla | Geometriske kandidatar utan nummerkrav | Tidlegare ukopla med anna nummer |
|---|---:|---:|---:|---:|
| 2013–2020 | 1 920 | 696 (36,3 %) | 1 289 (67,1 %) | 609 |
| 2021–3. oktober 2026 | 6 527 | 6 344 (97,2 %) | 6 359 (97,4 %) | 35 |

599 av dei 609 eldre kandidatane tilfredsstiller også start-/endepunktkontrollen. Dette er meldingsrader, ikkje uavhengige skred eller positive strekning–døgn. Summane er ikkje additive: når nummerkravet blir fjerna, blir nokre tidlegare koplingar tvitydige. Kandidatane er ikkje endeleg validerte historiske koplingar.

Vegvesenet si nummerliste stadfestar fleire observerte par: Fv241 → Fv5623 (50 kandidatrader), Fv337 → Fv5641 (34), og hovudparsell 4 av Fv152 → Fv5606 (40 geometriske kandidatrader på dette nummerparet). Fv152 er også delt mellom nye nummer; ein enkel global nummerordbok vil derfor kunne gi feil.

Kjelder:

- https://www.vegvesen.no/kjoretoy/yrkestransport/veglister-og-dispensasjoner/nye-vegnummer/
- https://labs.vegdata.no/nvdbstatus/regionreform/vegnummer/nyevegnummerlister/20210615%20Nye%20vegnummer%20-%20F14%20Sogn%20og%20Fjordane.pdf
- https://historiske-vegreferanser.atlas.vegvesen.no/docs/userdoc.html

## Tyding og vidare retting

Omnummerering er ein konkret og vesentleg årsak til tap i den eldre koplinga. Ho forklarer ikkje nødvendigvis heile tidsend­ringa: talet på eksplisitte skredmeldingar i kjelda aukar òg, og koordinat, historisk geometri og kategoriendringar kan gi andre tap. Analysen dekkjer 2013 og seinare; han dokumenterer ikkje skredfrie år før dette.

Neste kopling bør omsetje historiske referansar med gammalt fylke, vegkategori, nummer, dato og hovudparsell/meter der dei finst. Koordinat må kontrollere og skilje mellom alternative nye vegar. Behald opphavleg referanse og koplingsgrunnlag for revisjon. Etter retting må episodar og døgn byggjast på nytt, og tidsfordelinga vurderast før ny modelltrening.

## Positive døgn

Eit positivt strekning–døgn er éin kombinasjon av strekning og dato med minst éin skredepisode som er teken med i etiketten. Fleire episodar same dag på same strekning tel som eitt positivt døgn. Same dato på to strekningar tel som to. Ei fem dagar lang stenging gir ikkje automatisk fem positive døgn.

For vegmeldingar brukar dagens episodeheuristikk datoen for første positive melding, frå gyldig-frå-tidspunktet omrekna til norsk tid. Dette er ikkje nødvendigvis tidspunktet då skredet fysisk gjekk. Null betyr ingen skredepisode i det valde datagrunnlaget, ikkje dokumentert fråvær av skred.
