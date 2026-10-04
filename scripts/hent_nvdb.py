"""Hent NVDB-vegnett for Vestland og bygg etterprøvbare CSV-tabellar.

Skriptet bruker berre Python sitt standardbibliotek. Det har to hovudsteg:

1. ``download`` hentar alle API-sider for fylke 46 og eksisterande E-, R- og
   F-vegar. Originale svar blir lagra i data/raw/nvdb/, saman med eit manifest
   som dokumenterer førespurnad, uttakstid og SHA-256 for kvar side.
2. ``build`` les det fullførte råuttaket, kontrollerer hashane, vel køyrande
   vegtrasear og lagar segment-, delstreknings- og strekningsoversikter.

Køyring frå prosjektmappa::

    python scripts/hent_nvdb.py            # Nytt API-uttak og nye CSV-tabellar
    python scripts/hent_nvdb.py --offline  # Bygg frå eksisterande råsvar

Output i data/processed/: vegsegment.csv, delstrekningar.csv, strekningar.csv
og kvalitetsrapport.json. Køyring erstattar desse filene; rådata og tabellar
representerer eit datert vegnett, ikkje ei rekonstruert vegnetthistorie.

Strekningane er NVDB sine administrative einingar, ikkje faste 10 km-bitar.
Armar, parallelle løp og ferje kan vere med. Summert segmentlengd er derfor
ikkje nødvendigvis lengda av éin samanhengande hovudtrasé. Geometrien blir
bevart som WKT med opphavleg SRID; ingen koordinattransformasjon skjer her.
"""
import argparse
import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://nvdbapiles.atlas.vegvesen.no/vegnett/api/v4/veglenkesekvenser/segmentert'


def download(raw):
    """Hent alle sider og lagre rå JSON og manifest i den eksisterande mappa.

    ``raw`` er ein pathlib.Path. API-et returnerer opptil 1 000 segment per
    side. ``metadata.neste.start`` er ein sidepeikar, ikkje eit sidetal.
    Mellombelse nettfeil blir prøvde på nytt, opptil fem forsøk per side.
    Eit nytt manifest med complete=True blir skrive først etter fullført
    nedlasting. Køyr ikkje fleire nedlastingar mot same mappe samtidig.
    """
    # 46 = Vestland. E = europaveg, R = riksveg, F = fylkesveg;
    # fase V = eksisterande veg. Kommunale/private/skogsvegar er ikkje med.
    params = dict(fylke=46, vegsystemreferanse='EV,RV,FV', antall=1000)
    url = ENDPOINT + '?' + urlencode(params)
    pages = []
    seen = set()
    while url:
        # Stopp dersom pagineringa går i ring eller skiftar til ein annan vert.
        if url in seen or urlsplit(url).hostname != 'nvdbapiles.atlas.vegvesen.no':
            raise ValueError('Invalid pagination URL')
        seen.add(url)
        for attempt in range(5):
            try:
                req = Request(url, headers={'X-Client': 'aktsomhet-ml', 'Accept': 'application/json'})
                with urlopen(req, timeout=120) as response:
                    data = json.load(response)
                break
            except Exception:
                if attempt == 4:
                    raise
                # Vent 1, 2, 4 og 8 sekund ved feil før siste forsøk.
                time.sleep(2 ** attempt)
        page = raw / f'page_{len(pages)+1:04d}.json'
        page.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        # Hashen gjeld dei lagra byteane og blir kontrollert før tabellbygging.
        pages.append({'file': page.name, 'sha256': hashlib.sha256(page.read_bytes()).hexdigest(),
                      'count': len(data['objekter'])})
        print(f"Page {len(pages)}: {len(data['objekter'])} segments", flush=True)
        if not data['objekter']:
            break
        nxt = data.get('metadata', {}).get('neste', {})
        # Bygg neste URL frå sidepeikaren og dei same filtera. Nokre API-lenkjer
        # utelèt /api/v4; derfor bruker me vårt kjende endepunkt på kvar side.
        url = ENDPOINT + '?' + urlencode({**params, 'start': nxt['start']}) if nxt.get('start') else None
    manifest = dict(retrieved_utc=datetime.now(timezone.utc).isoformat(), endpoint=ENDPOINT,
                    parameters=params, pages=pages, complete=True)
    (raw / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def write_csv(path, rows):
    """Skriv tabellrader med felles feltnamn som UTF-8 med BOM.

    BOM gjer norsk tekst enklare å opne i Excel. CSV bruker komma som
    skiljeteikn og Python sine desimaltal med punktum. Tomme tabellar gir feil,
    slik at eit manglande uttak ikkje blir skjult av ei tom resultatfil.
    """
    if not rows:
        raise ValueError(f'No rows for {path}')
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows, by_subsection=False):
    """Samle segment på strekning, eller på delstrekning når flagget er True.

    ID-felta avgrensar gruppene. Lengd blir summert frå NVDB sine segment;
    arm=True går berre inn i arm_lengde_m, andre segment i hovudlop_lengde_m.
    Kommune-/delstrekningslister blir sorterte og skilde med '|'. Bounding
    box er samla utstrekning, ikkje eit representativt punkt for strekninga.

    Meterintervallet blir berre aggregert innan ei delstrekning. Meterverdiar
    på ulike delstrekningar har ikkje ein felles skala og blir ikkje summerte.
    """
    groups = defaultdict(list)
    for r in rows:
        groups[r['delstrekning_id'] if by_subsection else r['strekning_id']].append(r)
    result = []
    for key, parts in sorted(groups.items()):
        first = parts[0]
        item = dict(strekning_id=first['strekning_id'], fylke=46,
                    vegkategori=first['vegkategori'], fase=first['fase'],
                    vegnummer=first['vegnummer'], strekning=first['strekning'])
        if by_subsection:
            item.update(delstrekning_id=key, delstrekning=first['delstrekning'],
                        fra_meter=min(r['fra_meter'] for r in parts),
                        til_meter=max(r['til_meter'] for r in parts))
        item.update(delstrekningar='|'.join(map(str, sorted({r['delstrekning'] for r in parts}))),
                    kommunar='|'.join(map(str, sorted({r['kommune'] for r in parts}))),
                    segment_antal=len(parts), lengde_m=round(sum(r['lengde_m'] for r in parts), 3),
                    hovudlop_lengde_m=round(sum(r['lengde_m'] for r in parts if not r['arm']), 3),
                    arm_lengde_m=round(sum(r['lengde_m'] for r in parts if r['arm']), 3),
                    srid='|'.join(map(str, sorted({r['srid'] for r in parts}))),
                    xmin=min(r['xmin'] for r in parts), ymin=min(r['ymin'] for r in parts),
                    xmax=max(r['xmax'] for r in parts), ymax=max(r['ymax'] for r in parts))
        result.append(item)
    return result


def build(raw, out):
    """Bygg alle tre vegtabellane frå eit kontrollert, fullført råuttak.

    ``raw`` og ``out`` er eksisterande mapper (pathlib.Path). Innan dei
    nedlasta E/R/F-vegane beheld me berre segment med strekning, utan kryss
    eller sideanlegg, for køyrande trafikantgruppe K på nivå Vegtrase.
    Utelatingar blir talde i kvalitetsrapporten; råsvara blir ikkje endra.

    Ein segmentnøkkel kombinerer veglenkesekvensid, veglenkenummer og
    segmentnummer. Strekningsnøkkelen kombinerer fylke, kategori, fase,
    vegnummer og strekning, til dømes 46_FV5623_S1. Delstrekninga legg til D.
    Hashar, duplikatnøklar, fylke/kategori/fase og lengdesummar blir kontrollerte.
    """
    manifest = json.loads((raw / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['complete']
    rows, excluded, seen = [], Counter(), set()
    for page in manifest['pages']:
        content = (raw / page['file']).read_bytes()
        assert hashlib.sha256(content).hexdigest() == page['sha256']
        for s in json.loads(content)['objekter']:
            ref = s.get('vegsystemreferanse', {})
            road, section = ref.get('vegsystem', {}), ref.get('strekning', {})
            # Desse referansetypane passar ikkje i strekning/delstrekning-tabellen.
            if not section or ref.get('kryssystem') or ref.get('sideanlegg'):
                excluded['kryss_sideanlegg_utan_strekning'] += 1
                continue
            if section.get('trafikantgruppe') != 'K':
                excluded['ikkje_koyrande'] += 1
                continue
            if s.get('topologinivå') != 'Vegtrase':
                excluded['ikkje_vegtrase'] += 1
                continue
            assert s['fylke'] == 46 and road['vegkategori'] in 'ERF' and road['fase'] == 'V'
            identity = (s['veglenkesekvensid'], s['veglenkenummer'], s['segmentnummer'])
            assert identity not in seen, identity
            seen.add(identity)
            geom = s['geometri']
            wkt = geom['wkt']
            if not wkt.startswith('LINESTRING'):
                raise ValueError(f'Unexpected geometry: {wkt[:60]}')
            # Les x/y til utstrekninga, men bevar heile WKT-en, også eventuell z.
            # API-geometrien har oppgitt SRID; x/y er ikkje nødvendigvis lon/lat.
            coords = [list(map(float, p.split())) for p in wkt[wkt.index('(')+1:wkt.rindex(')')].split(',')]
            sid = f"46_{road['vegkategori']}{road['fase']}{road['nummer']}_S{section['strekning']}"
            rows.append(dict(segment_id='-'.join(map(str, identity)), strekning_id=sid,
                delstrekning_id=f"{sid}_D{section['delstrekning']}", fylke=46, kommune=s['kommune'],
                vegkategori=road['vegkategori'], fase=road['fase'], vegnummer=road['nummer'],
                strekning=section['strekning'], delstrekning=section['delstrekning'],
                fra_meter=section['fra_meter'], til_meter=section['til_meter'],
                lengde_m=s['lengde'], arm=section['arm'], adskilte_lop=section.get('adskilte_løp'),
                retning=section['retning'], type_veg=s['typeVeg'], lenketype=s['type'],
                medium=geom.get('medium', ''), srid=geom['srid'],
                xmin=min(p[0] for p in coords), ymin=min(p[1] for p in coords),
                xmax=max(p[0] for p in coords), ymax=max(p[1] for p in coords), geometri_wkt=wkt))
    # Eitt detaljert segmentgrunnlag er kjelda til begge aggregeringsnivåa.
    sections = aggregate(rows)
    subsections = aggregate(rows, True)
    write_csv(out / 'vegsegment.csv', rows)
    write_csv(out / 'delstrekningar.csv', subsections)
    write_csv(out / 'strekningar.csv', sections)
    assert len({r['strekning_id'] for r in sections}) == len(sections)
    # CSV-gruppene er avrunda til millimeter; tillat denne avrundingsskilnaden.
    assert abs(sum(r['lengde_m'] for r in rows) - sum(r['lengde_m'] for r in sections)) < len(sections)*0.001
    report = dict(segment=len(rows), delstrekningar=len(subsections), strekningar=len(sections),
                  total_lengde_km=sum(r['lengde_m'] for r in rows)/1000,
                  vegkategori=dict(Counter(r['vegkategori'] for r in sections)),
                  ekskludert=dict(excluded), srid=sorted({r['srid'] for r in rows}),
                  min_strekningslengde_m=min(r['lengde_m'] for r in sections),
                  maks_strekningslengde_m=max(r['lengde_m'] for r in sections))
    (out / 'kvalitetsrapport.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hent NVDB-vegnett for Vestland og bygg segment-/streknings-CSV.')
    parser.add_argument('--offline', action='store_true', help='Bygg tabellane frå lagra råsvar utan nettverk')
    args = parser.parse_args()
    raw, out = ROOT / 'data/raw/nvdb', ROOT / 'data/processed'
    raw.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    if not args.offline:
        download(raw)
    build(raw, out)
