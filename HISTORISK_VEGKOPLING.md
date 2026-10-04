# Retting av historiske vegkoplingar

Køyrt og kontrollert 4. oktober 2026. Reformkoplinga er aktiv i `filtrer_xgeo_vegmeldingar.py`.

## Metode

Dei offisielle PDF-listene for Hordaland og Sogn og Fjordane er lagra med kjeldeadresse og SHA-256 i `data/raw/historiske_vegnummer/`. Dei gir 675 ERF-konverteringsrader; to overgangar til privatveg er utanfor vegutvalet.

Vegkategori blir bevart. Gammalt fylke blir utleidd frå kommunen på den aktuelle veggeometrien, ikkje frå eit vegnummer åleine. Ved fylkesgrense i ei strekning blir næraste kommunegruppe brukt berre når avstandsskilnaden er minst 20 meter. Eit nummer kan ha fleire nye greinnummer: alle dokumenterte alternativ blir vurderte geografisk saman med direkte treff på dagens nummer. Det krevst avstand høgst 100 meter og margin minst 20 meter til neste tillatne strekning. Start-/endepunktkontrollen er uendra.

Xgeo-radene har ikkje hovudparsell eller meterverdi. Dette er derfor reformalias med geografisk kontroll, ikkje fullstendig historisk vegreferansekonvertering. Listene opplyser at endringsdato i NVDB kan skilje seg frå gyldigheitsdato. Me tillèt gamle alias fram til 31. desember 2021 som ei eksplisitt overgangsregel. Datoen og bruk etter oppgitt NVDB-endringsdato er lagra per rad. 25 strenge historiske meldingsrader er etter oppgitt endringsdato. Frå 2022 blir ikkje gamle alias automatisk brukte.

## Resultat

- 1 218 meldingsrader er kopla med dokumentert historisk nummer  av desse 618 i strengt utval.
- 1 217 nye koplingar, éi omplassering og tre fjerna tvitydige koplingar. Dei fire endringane av tidlegare kopla rader gjeld ikkje strenge positive rader.
- Positive strekning–døgn: 4 234 → 4 522, 288 nye og ingen tapte.
- I 2013–2020: 311 → 599. Frå 2021 er døgnutfallet uendra.

| År | Før | Etter | Endring |
|---|---:|---:|---:|
| 2013 | 41 | 75 | +34 |
| 2014 | 24 | 49 | +25 |
| 2015 | 40 | 95 | +55 |
| 2016 | 42 | 86 | +44 |
| 2017 | 31 | 69 | +38 |
| 2018 | 40 | 101 | +61 |
| 2019 | 31 | 61 | +30 |
| 2020 | 62 | 63 | +1 |
| 2021 | 158 | 158 | +0 |
| 2022 | 544 | 544 | +0 |
| 2023 | 849 | 849 | +0 |
| 2024 | 1067 | 1067 | +0 |
| 2025 | 699 | 699 | +0 |
| 2026 | 606 | 606 | +0 |

## Etterprøving og filer

Originale meldingsfelt (`ROAD_TYPE`, `ROAD_NUMBER`, koordinat og dato) er bevart. Nye felt omfattar `kopla_vegnummer`, `historisk_omnummerering`, `historisk_fylke`, `nummeroversikt_rader`, `nummeroversikt_kjelde`, `nummer_endra_nvdb_dato`, `historisk_etter_nvdb_endring`, `historisk_datoregel` og `kopling_margin_m`. `historisk_hp_meter_tilgjengeleg` er false fordi kjelda ikkje inneheld desse felta.

- `data/processed/vegmeldingar_foer_historisk/`: komplett før-snapshot av behandla vegmeldingar, inkludert tidlegare manuell kontrollfil.
- `data/processed/vegmeldingar/historiske_nummeroversikt.csv`: tabulert kjeldeoversikt med gamle hovudparsell-/metergrenser.
- `historiske_koplingsendringar.csv`: endra meldingskoplingar med før-/etter-ID.
- `historiske_dognendringar.csv` og `historisk_kopling_per_ar.csv`: før-/etter-etikettar og årstal.
- `historisk_validering.json` og `validation_report.json`: kontrollresultat.

Begge valideringsskripta har passert. Dei kontrollerer mellom anna publiserte nummerpar, splitta vegar, fylkesskilje, riksveg/fylkesveg, datoregelen, originale referansar, avstand/margin, episodar og døgn. Alle årlege alternative etikettpanel er bygde på nytt, og originale NVDB-etikettar og vêrdata er bevart. Dette er teknisk validering; koordinat og meldingstekst er framleis ikkje manuelt stadfesta for kvar hending.

Notebooken viser den nye koplingsmetoden og før-/etter-tabellen. Eksisterande modellresultat er framleis frå NVDB-utfallet; ingen ny vegmeldingsmodell er trena i denne rettinga.

## Kjelder

- [Hordaland, offisiell reformliste](https://labs.vegdata.no/nvdbstatus/regionreform/vegnummer/nyevegnummerlister/20210615%20Nye%20vegnummer%20-%20F12%20Hordaland.pdf)
- [Sogn og Fjordane, offisiell reformliste](https://labs.vegdata.no/nvdbstatus/regionreform/vegnummer/nyevegnummerlister/20210615%20Nye%20vegnummer%20-%20F14%20Sogn%20og%20Fjordane.pdf)
- [Kommunenummer og samanslåingar](https://www.regjeringen.no/no/tema/kommuner-og-regioner/kommunestruktur/nyekommuneogfylkesnummer/id2629203/)

## Køyring

```powershell
# Hent og trekk ut PDF-tabellar med bundled Python og pdfplumber:
# python scripts/hent_historiske_vegnummer.py
.venv/Scripts/python.exe scripts/filtrer_xgeo_vegmeldingar.py
.venv/Scripts/python.exe scripts/valider_historisk_kopling.py
.venv/Scripts/python.exe scripts/valider_vegmeldingar.py
```
