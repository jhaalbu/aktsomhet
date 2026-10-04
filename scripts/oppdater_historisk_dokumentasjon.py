"""Refresh result documentation from the persisted corrected pipeline."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'data/processed/vegmeldingar'
report = json.loads((OUT/'historisk_validering.json').read_text())
filter_report = json.loads((OUT/'filterrapport.json').read_text())
annual = pd.read_csv(OUT/'historisk_kopling_per_ar.csv')
source_years = pd.read_csv(OUT/'kjeldesamanlikning_per_ar.csv')
doc = ROOT/'VEGMELDINGAR_UTTAK.md'
text = doc.read_text(encoding='utf-8')
text = text.replace('1. Same vegkategori og vegnummer som ei eksisterande strekning.',
    '1. Same vegkategori, og dagens vegnummer eller eit dokumentert historisk nummer frå reformlistene. Gammalt fylke blir kontrollert mot kommunen på veggeometrien. Gamle alias er tillatne til og med 2021; seinare bruk blir ikkje automatisk omsett.')
text = text.replace('på same veg,','blant tillatne noverande og historiske nummer,')
text = text.replace('17 863 kandidatpostar får ei vegkopling; 1 769 av desse har grov utstrekning.',
    '19 077 kandidatpostar får ei vegkopling; 1 802 av desse har grov utstrekning.')
text = text.replace('Gamle vegnummer, flytta vegar og omnummereringar kan gi manglande kopling.',
    'Reformnummer frå Hordaland og Sogn og Fjordane er no omsette med geografisk kontroll. Flytta vegar, kategoriendringar og omnummereringar utanfor listene kan framleis gi manglande kopling.')
text = text.replace('**6 573 meldingar**, samla til **4 486\nepisodekandidatar**, på 548 strekningar.',
    '**7 191 meldingar**, samla til **4 787\nepisodekandidatar**, på 562 strekningar.')
for old,new in [('4 234','4 522'),('3 206','3 388'),('1 028','1 134'),('9 346','9 240'),('13 580','13 762')]:
    text = text.replace(old,new)
text = text.replace('| 2013–2020 | 311 | 5 221 |','| 2013–2020 | 599 | 5 221 |')
text = text.replace('Både kjeldepraksis og historiske vegnummer kan påverke denne utviklinga.',
    'Den historiske nummerrettinga auka 2013–2020 frå 311 til 599 positive døgn. Kjeldepraksis og andre historiske endringar kan framleis påverke utviklinga.')
doc.write_text(text,encoding='utf-8')

lines = ['# Retting av historiske vegkoplingar', '',
    'Køyrt og kontrollert 4. oktober 2026. Reformkoplinga er aktiv i `filtrer_xgeo_vegmeldingar.py`.', '',
    '## Metode', '',
    'Dei offisielle PDF-listene for Hordaland og Sogn og Fjordane er lagra med kjeldeadresse og SHA-256 i `data/raw/historiske_vegnummer/`. Dei gir 675 ERF-konverteringsrader; to overgangar til privatveg er utanfor vegutvalet.', '',
    'Vegkategori blir bevart. Gammalt fylke blir utleidd frå kommunen på den aktuelle veggeometrien, ikkje frå eit vegnummer åleine. Ved fylkesgrense i ei strekning blir næraste kommunegruppe brukt berre når avstandsskilnaden er minst 20 meter. Eit nummer kan ha fleire nye greinnummer: alle dokumenterte alternativ blir vurderte geografisk saman med direkte treff på dagens nummer. Det krevst avstand høgst 100 meter og margin minst 20 meter til neste tillatne strekning. Start-/endepunktkontrollen er uendra.', '',
    'Xgeo-radene har ikkje hovudparsell eller meterverdi. Dette er derfor reformalias med geografisk kontroll, ikkje fullstendig historisk vegreferansekonvertering. Listene opplyser at endringsdato i NVDB kan skilje seg frå gyldigheitsdato. Me tillèt gamle alias fram til 31. desember 2021 som ei eksplisitt overgangsregel. Datoen og bruk etter oppgitt NVDB-endringsdato er lagra per rad. 25 strenge historiske meldingsrader er etter oppgitt endringsdato. Frå 2022 blir ikkje gamle alias automatisk brukte.', '',
    '## Resultat', '',
    f'- {report["historically_linked_rows"]:,} meldingsrader er kopla med dokumentert historisk nummer, av desse {report["historical_strict_rows"]} i strengt utval.'.replace(',', ' '),
    '- 1 217 nye koplingar, éi omplassering og tre fjerna tvitydige koplingar. Dei fire endringane av tidlegare kopla rader gjeld ikkje strenge positive rader.',
    '- Positive strekning–døgn: 4 234 → 4 522, 288 nye og ingen tapte.',
    '- I 2013–2020: 311 → 599. Frå 2021 er døgnutfallet uendra.', '',
    '| År | Før | Etter | Endring |','|---|---:|---:|---:|']
for row in annual.itertuples():
    lines.append(f'| {row.year} | {row.before_positive_days} | {row.after_positive_days} | {row.net_change:+d} |')
lines += ['', '## Etterprøving og filer', '',
    'Originale meldingsfelt (`ROAD_TYPE`, `ROAD_NUMBER`, koordinat og dato) er bevart. Nye felt omfattar `kopla_vegnummer`, `historisk_omnummerering`, `historisk_fylke`, `nummeroversikt_rader`, `nummeroversikt_kjelde`, `nummer_endra_nvdb_dato`, `historisk_etter_nvdb_endring`, `historisk_datoregel` og `kopling_margin_m`. `historisk_hp_meter_tilgjengeleg` er false fordi kjelda ikkje inneheld desse felta.', '',
    '- `data/processed/vegmeldingar_foer_historisk/`: komplett før-snapshot av behandla vegmeldingar, inkludert tidlegare manuell kontrollfil.',
    '- `data/processed/vegmeldingar/historiske_nummeroversikt.csv`: tabulert kjeldeoversikt med gamle hovudparsell-/metergrenser.',
    '- `historiske_koplingsendringar.csv`: endra meldingskoplingar med før-/etter-ID.',
    '- `historiske_dognendringar.csv` og `historisk_kopling_per_ar.csv`: før-/etter-etikettar og årstal.',
    '- `historisk_validering.json` og `validation_report.json`: kontrollresultat.', '',
    'Begge valideringsskripta har passert. Dei kontrollerer mellom anna publiserte nummerpar, splitta vegar, fylkesskilje, riksveg/fylkesveg, datoregelen, originale referansar, avstand/margin, episodar og døgn. Alle årlege alternative etikettpanel er bygde på nytt, og originale NVDB-etikettar og vêrdata er bevart. Dette er teknisk validering; koordinat og meldingstekst er framleis ikkje manuelt stadfesta for kvar hending.', '',
    'Notebooken viser den nye koplingsmetoden og før-/etter-tabellen. Eksisterande modellresultat er framleis frå NVDB-utfallet; ingen ny vegmeldingsmodell er trena i denne rettinga.', '',
    '## Kjelder', '',
    '- [Hordaland, offisiell reformliste](https://labs.vegdata.no/nvdbstatus/regionreform/vegnummer/nyevegnummerlister/20210615%20Nye%20vegnummer%20-%20F12%20Hordaland.pdf)',
    '- [Sogn og Fjordane, offisiell reformliste](https://labs.vegdata.no/nvdbstatus/regionreform/vegnummer/nyevegnummerlister/20210615%20Nye%20vegnummer%20-%20F14%20Sogn%20og%20Fjordane.pdf)',
    '- [Kommunenummer og samanslåingar](https://www.regjeringen.no/no/tema/kommuner-og-regioner/kommunestruktur/nyekommuneogfylkesnummer/id2629203/)', '',
    '## Køyring', '', '```powershell',
    '# Hent og trekk ut PDF-tabellar med bundled Python og pdfplumber:',
    '# python scripts/hent_historiske_vegnummer.py',
    '.venv/Scripts/python.exe scripts/filtrer_xgeo_vegmeldingar.py',
    '.venv/Scripts/python.exe scripts/valider_historisk_kopling.py',
    '.venv/Scripts/python.exe scripts/valider_vegmeldingar.py',
    '```', '']
(ROOT/'HISTORISK_VEGKOPLING.md').write_text('\n'.join(lines),encoding='utf-8')
readme = ROOT/'README.md'
text = readme.read_text(encoding='utf-8')
note = '\nHistoriske vegmeldingar er no kopla med dei offisielle reformlistene og geografisk kontroll. Sjå [HISTORISK_VEGKOPLING.md](HISTORISK_VEGKOPLING.md) for metode, før-/etter-tal og kontrollar.\n'
if 'HISTORISK_VEGKOPLING.md' not in text:
    text += note
readme.write_text(text,encoding='utf-8')
diagnosis = ROOT/'VEGNUMMER_DIAGNOSE.md'
text = diagnosis.read_text(encoding='utf-8')
if 'HISTORISK_VEGKOPLING.md' not in text:
    text = text.replace('Produksjonsetikettane er ikkje endra.', 'Dette er den opphavlege diagnosen før retting. Rettinga er no gjennomført; sjå [HISTORISK_VEGKOPLING.md](HISTORISK_VEGKOPLING.md).')
diagnosis.write_text(text,encoding='utf-8')
print('Updated result documentation')
