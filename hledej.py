#!/usr/bin/env python3
"""CLI pro hledani v lecivech.

Zretezi router a hybridni hledani a vypise obojí - nejdriv CO ROZHODL
ROUTER, pak ohodnocene vysledky seskupene po lecivech.

Vypis routeru neni ozdoba: kdyz hledani nic nenajde, uzivatel MUSI videt,
cim se filtrovalo. Jinak nepozna rozdil mezi "takovy lek neexistuje"
a "spatne jsem se zeptal".

Vysledky jsou seskupene PO LECICH, ne po pasazich. Tabulka ma jeden radek
na polozku, takze bez seskupeni by top-10 mohlo byt osm radku Paralenu.
Proto se hleda s rezervou a seskupuje se az potom.

Pouziti:
  uv run python hledej.py "volne prodejny lek na bolest"
  uv run python hledej.py "bolest bricha nezadouci ucinek" --prah 0.6
  uv run python hledej.py "Paralen 500mg" --pasaze
  uv run python hledej.py "bolest hlavy" --bez-routeru
  uv run python hledej.py "bolest" --vaha-semantika 0.95
"""

import io
import sys
import json
import argparse
from pathlib import Path

from common.config import MODEL_EMBED, MODEL_ROUTER
from common.hledani import Filtr, hledej, seskup, NAZEV_SEKCE
from common.ollama_client import priprav_modely as _priprav_modely
from common.router import rozhodni

# Hleda se s rezervou, aby melo seskupeni z ceho vybirat.
REZERVA = 60


# Modely, ktere musi byt v pameti, aby dotaz nestal: router (generativni)
# a embedding. Stejny seznam potrebuje i GUI pri startu aplikace.
MODELY_PRO_DOTAZ = (MODEL_ROUTER, MODEL_EMBED)


def priprav_modely(*, tichy: bool = False) -> None:
    """Predehreje modely a vypise, co se delo. Vlastni praci dela
    `ollama_client.priprav_modely()`, aby ji mohlo pouzit i GUI."""
    stavy = _priprav_modely(
        MODELY_PRO_DOTAZ,
        hlas=None if tichy else lambda t: print(t, flush=True),
    )
    for st in stavy:
        if not st.ok:
            print(f"  POZOR: {st.model} se nepodarilo nahrat ({st.chyba})",
                  file=sys.stderr)
    if not tichy and any(st.nacital_se and st.ok for st in stavy):
        print(flush=True)


def _adresar(kod: str) -> str:
    for p in Path("data/leciva").glob(f"{kod}_*"):
        return str(p).replace("\\", "/")
    return f"data/leciva/{kod}"


def vypis_atc_zachranu(dotaz: str, filtr=None) -> None:
    """Zachranna sit: kdyz nic nesedi, nabidnout aspon terapeutickou skupinu.

    Vypisuje se ZVLAST a oznacene, protoze to NENI nalez v dokumentu -
    je to nase odvozeni z ATC skupiny, kterou lecivu priradil SUKL.
    Michat to mezi nalezy ze SPC by znicilo dohledatelnost, ktera je
    hlavni prednosti celeho reseni.
    """
    import psycopg
    from common.config import PG_DSN
    from common.dotazy import atc_pro_dotaz, nacti_atc

    prefixy = atc_pro_dotaz(dotaz)
    if not prefixy:
        return
    popisy = {}
    import json as _json
    from pathlib import Path as _Path
    if _Path("atc_mapa.json").exists():
        popisy = {k: v.get("popis", "")
                  for k, v in _json.loads(
                      _Path("atc_mapa.json").read_text(encoding="utf-8")).items()
                  if isinstance(v, dict)}

    print()
    print("-" * 78)
    print("PODLE TERAPEUTICKE SKUPINY (odvozeno z ATC, NENI to udaj ze SPC)")
    print("-" * 78)
    # Filtr uzivatele MUSI platit i tady. Bez toho by sit na dotaz
    # "hrazene antibiotikum" nabidla i nehrazeny AMOKSIKLAV, tedy presny
    # opak toho, co clovek chtel.
    kde, par = ["atc LIKE %(atc)s"], {}
    if filtr is not None:
        if filtr.na_predpis is not None:
            kde.append("na_predpis = %(na_predpis)s")
            par["na_predpis"] = filtr.na_predpis
        if filtr.hrazeno is not None:
            kde.append("hrazeno = %(hrazeno)s")
            par["hrazeno"] = filtr.hrazeno

    with psycopg.connect(PG_DSN) as c:
        for atc in prefixy:
            par["atc"] = atc + "%"
            leky = c.execute(
                "SELECT nazev, sila, atc, na_predpis, hrazeno FROM leciva "
                f"WHERE {' AND '.join(kde)} ORDER BY nazev", par).fetchall()
            if not leky:
                continue
            print(f"  {atc} - {popisy.get(atc, '')}")
            for nazev, sila, plny, np, hr in leky:
                vydej = {True: "Rx", False: "OTC"}.get(np, "?")
                hrazeni = {True: "hrazený", False: "nehrazený"}.get(hr, "?")
                print(f"      {nazev} {sila or ''}".rstrip()
                      + f"  ·  {vydej} · {hrazeni} · ATC {plny}")
    print()
    print("  Pozor: skupina rika, k cemu se leciva TOHOTO DRUHU pouzivaji.")
    print("  Neni to indikace z prislusneho SPC - tu je potreba overit.")


def vypis_router(dotaz: str, filtr: Filtr, jistota: str, syrove: dict) -> None:
    print("=" * 78)
    print(f"DOTAZ: {dotaz}")
    print("=" * 78)
    print("ROUTER")
    if "chyba" in syrove:
        print(f"  SELHAL: {syrove['chyba']}")
        print("  -> hleda se ve VSECH sekcich, bez filtru")
    else:
        print(f"  sekce            {', '.join(filtr.sekce) if filtr.sekce else 'VSECHNY (nizka jistota)'}")
        print(f"  text pro vektor  {syrove.get('dotaz_text')!r}")
        print(f"  jistota          {jistota}")
        print(f"  filtr            {filtr.popis()}")
    nacitani = syrove.get("_nacitani_modelu_s")
    if nacitani:
        print(f"  POZN: model se musel načíst z disku ({nacitani} s). "
              f"Další dotaz už bude rychlý.")
    print()


def vypis_vysledky(o, leciva, *, pasaze: bool, zpusob: str = "rrf") -> None:
    if o.prazdna_kvuli_filtru:
        # Zadani: prazdny vysledek z filtru se MUSI rict natvrdo,
        # vcetne pouziteho filtru - uzivatel jinak nepozna, proc.
        print("NENALEZENO NIC.")
        print(f"Filtr nepustil dal ani jeden zaznam: {o.filtr.popis()}")
        print("Zkuste dotaz bez omezeni (napr. bez sily nebo bez 'volne prodejny').")
        vypis_atc_zachranu(o.dotaz, o.filtr)
        return

    if o.prazdna_kvuli_prahu:
        print(f"NENALEZENO NIC DOST PODOBNEHO.")
        print(f"Filtrem proslo {o.kandidatu_pred_prahem} zaznamu, ale zadny "
              f"nedosahl prahu podobnosti {o.prah:.2f}.")
        print("Zkuste jina slova, nebo snizte prah prepinacem --prah.")
        vypis_atc_zachranu(o.dotaz, o.filtr)
        return

    print(f"VYSLEDKY  ({len(leciva)} leciv z {o.kandidatu_pred_prahem} "
          f"zaznamu po filtru, razeno podle {zpusob})")
    print("-" * 78)

    # Surove RRF skore je kolem 0,016 a rozdily jsou v patem desetinnem
    # miste - necitelne. Prepocita se proto na 0-100 vuci nejlepsimu
    # vysledku, at je videt ODSTUP, ne absolutni hodnota (ta stejne nic
    # nerika, RRF neni pravdepodobnost ani podobnost).
    nejlepsi_skore = max((l.skore for l in leciva), default=1.0) or 1.0

    for i, l in enumerate(leciva, 1):
        v = l.nejlepsi
        rel = 100.0 * l.skore / nejlepsi_skore
        print(f"{i:2}. {l.nazev} {l.sila or ''}".rstrip())
        # Zakladni udaje o lecivu z API SUKL. Vsechno na dvou radcich,
        # at to nezere zbytecne misto - vydej a hrazeni jsou DVE ruzne
        # veci a plete se to, proto jsou vedle sebe.
        vydej = {True: "Rx (na předpis)", False: "OTC (volně prodejný)"}.get(
            v.na_predpis, "výdej neurčen")
        hrazeni = {True: "hrazený", False: "nehrazený"}.get(
            v.hrazeno, "hrazení neurčeno")
        udaje = " · ".join(x for x in (l.kod_sukl, vydej, hrazeni,
                                       f"ATC {v.atc}" if v.atc else None) if x)
        print(f"    kod SUKL   {udaje}")
        if v.ucinne_latky:
            print(f"    látky      {', '.join(v.ucinne_latky)}")
        print(f"    poradi     {rel:5.1f} / 100   (odstup od nejlepsiho)")
        print(f"    sémantika  {v.cosine:.3f} cosine     "
              f"pořadí #{v.poradi_sem or '-'}")
        fts = (f"{v.fts:.4f} ts_rank     pořadí #{v.poradi_fts}"
               if v.poradi_fts else "     –           nenašel")
        print(f"    fulltext   {fts}")
        print(f"    sekce      {NAZEV_SEKCE.get(v.sekce, v.sekce)}")

        radek = f"    nalezeno   {v.obsah_text}"
        if v.frekvence:
            radek += f"   [{v.frekvence}]"
        if v.organovy_system:
            radek += f"   [{v.organovy_system}]"
        print(radek)

        if v.sekce_atributy:
            skup = v.sekce_atributy.get("skupina")
            if skup and skup != "není uvedeno":
                print(f"    pro koho   {skup}")

        print(f"    zdroj      {l.odkaz(_adresar(l.kod_sukl))}")

        if pasaze and l.dalsi:
            print(f"    dalsi shody ({len(l.dalsi)}):")
            for d in l.dalsi:
                print(f"        {d.cosine:.3f}  {NAZEV_SEKCE.get(d.sekce, d.sekce)[:22]:22} "
                      f"{d.obsah_text[:44]}")
        print()


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # nargs="*" a ne "+": pri "+" argparse pozicni argument uzavre na prvnim
    # prepinaci, takze "hledej.py mam --zpusob cosine \"kopřivka\"" skoncilo
    # chybou "unrecognized arguments". Zbytek se dosbira z parse_known_args.
    p.add_argument("dotaz", nargs="*", help="text dotazu (uvozovky nejsou nutne)")
    p.add_argument("--leciv", type=int, default=10, help="kolik leciv vratit")
    p.add_argument("--prah", type=float, default=0.55,
                   help="minimalni podobnost (vychozi 0.55 - namerena hodnota, viz evaluate.py --prahy; 0 = vypnout)")
    p.add_argument("--vaha-semantika", type=float, default=None,
                   help="0..1, kolik vahy ma semantika proti fulltextu")
    p.add_argument("--zpusob", choices=["rrf", "cosine"], default="rrf",
                   help="razeni: rrf = fuze obou zebricku (default), "
                        "cosine = poradi urcuje jen podobnost")
    p.add_argument("--pasaze", action="store_true",
                   help="ukazat i dalsi shody u kazdeho leciva")
    p.add_argument("--bez-routeru", action="store_true",
                   help="hledat celym dotazem bez filtru")
    p.add_argument("--json", action="store_true", help="vystup jako JSON")
    p.add_argument("--nahrej", action="store_true",
                   help="jen nahrát modely do paměti a skončit (před demem)")
    p.add_argument("--bez-kontroly-modelu", action="store_true",
                   help="přeskočit úvodní ověření, že jsou modely v paměti")
    a, zbytek = p.parse_known_args()

    if a.nahrej:
        priprav_modely()
        print("Modely jsou v paměti, hledání teď poběží rychle.")
        return 0

    # Cokoli, co neni prepinac, patri do dotazu - at uz to uzivatel napsal
    # pred prepinacem, za nim, nebo uprostred.
    nezname = [z for z in zbytek if z.startswith("-")]
    if nezname:
        p.error("neznámý přepínač: " + " ".join(nezname))

    dotaz = " ".join(list(a.dotaz) + [z for z in zbytek if not z.startswith("-")]).strip()
    if not dotaz:
        p.error("chybí dotaz. Příklad: hledej.py \"volně prodejný lék na bolest\"")

    if not a.bez_kontroly_modelu:
        priprav_modely(tichy=a.json)

    if a.bez_routeru:
        filtr, jistota, syrove = Filtr(), "vypnuto", {"dotaz_text": dotaz}
    else:
        filtr, jistota, syrove = rozhodni(dotaz)

    if not a.json:
        vypis_router(dotaz, filtr, jistota, syrove)

    kw = {"zpusob": a.zpusob}
    if a.vaha_semantika is not None:
        kw["vaha_semantika"] = a.vaha_semantika

    o = hledej(syrove.get("dotaz_text") or dotaz, filtr=filtr,
               puvodni_dotaz=dotaz,
               limit=REZERVA, prah=a.prah, **kw)
    leciva = seskup(o.vysledky, leciv=a.leciv)

    if a.json:
        print(json.dumps({
            "dotaz": dotaz,
            "router": {"sekce": filtr.sekce, "jistota": jistota,
                       "dotaz_text": syrove.get("dotaz_text"),
                       "filtr": filtr.popis()},
            "kandidatu": o.kandidatu_pred_prahem,
            "leciva": [{
                "kod_sukl": l.kod_sukl, "nazev": l.nazev, "sila": l.sila,
                "cosine": round(l.nejlepsi.cosine, 4),
                "skore_rel": round(100.0 * l.skore / max(
                    (x.skore for x in leciva), default=1.0), 1),
                "sekce": l.nejlepsi.sekce,
                "obsah": l.nejlepsi.obsah_text,
                "frekvence": l.nejlepsi.frekvence,
                "organovy_system": l.nejlepsi.organovy_system,
                "zdroj": l.odkaz(_adresar(l.kod_sukl)),
                "dalsich_pasazi": len(l.dalsi),
            } for l in leciva],
        }, ensure_ascii=False, indent=1))
        return 0

    vypis_vysledky(o, leciva, pasaze=a.pasaze, zpusob=a.zpusob)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
