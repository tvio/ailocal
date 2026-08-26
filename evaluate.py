#!/usr/bin/env python3
"""Krok 15: evaluace - jak poznat, ze to funguje.

Klicova myslenka ze zadani: DOSLOVNA SHODA JE SPODNI HRANICE.
Kdyz semanticke hledani nenajde lek, ktery hledane slovo obsahuje
DOSLOVA, je to jednoznacna chyba - bez lidskeho posuzovani. Semantika
smi najit VIC (synonyma, parafraze), ale nesmi ztratit to, co je
v datech napsane. Diky tomu jde vetsina pravdy odvodit z databaze
a rucni prace zbyde na minimum.

POZOR NA PORADI: kdyz TEST 0 hlasi diry v datech, cisla z testu 1-4
nemaji smysl interpretovat jako kvalitu hledani. Lek, ktery v datech
neni, nemuze byt nalezen - a vypadalo by to jako chyba vyhledavani,
i kdyz je chyba v extrakci.

Pustit po KAZDE zmene promptu, modelu, chunkovani nebo vah RRF.

Pouziti:
  uv run python evaluate.py                  # vsechny testy
  uv run python evaluate.py --jen 0          # jen kvalita dat (rychle, bez modelu)
  uv run python evaluate.py --pocet 200      # vic auto-dotazu v testu 2
  uv run python evaluate.py --prahy          # zmerit prah podobnosti
  uv run python evaluate.py --vahy           # porovnat zpusoby razeni
"""

import io
import sys
import json
import random
import argparse
from dataclasses import dataclass

import psycopg

from common.config import PG_DSN
from common.hledani import Filtr, hledej, seskup

# --- TEST 3: negativni dotazy ------------------------------------------------
# Temata, ktera v korpusu NEJSOU. Spravna odpoved je "nenasli jsme nic".
# Podle zadani je tohle na demu NEJSILNEJSI test: kdyz system na neexistujici
# tema rekne "nemam", je to presvedcivejsi dukaz, ze nefabuluje, nez deset
# spravnych odpovedi. Zaroven je to jediny test, ktery overi PRAH.
# POZOR: negativni dotaz se MUSI OVERIT proti datum, ne odhadnout.
# Prvni verze mela 5 dotazu a CTYRI z nich byly v datech:
#     "zlomenina nohy"   -> CONTROLOC ma "zlomeniny kycelni kosti" jako NU
#     "ockovani"         -> ADVANTAN ma "reakce kuze po ockovani"
#     "hubnuti"          -> ABLYMICO (liraglutid) na hubnuti PRIMO JE
#     "vypadavani vlasu" -> ADVANTAN ma "zanet vlasoveho vacku"
# System odpovidal spravne a test to pocital jako selhani - a tim se
# znehodnotilo mereni prahu. V korpusu se stovkami nezadoucich ucinku
# se skoro kazde lekarske tema nekde vyskytne.
#
# Nize jsou temata OVERENA jako nepritomna (viz overit_negativni()).
NEGATIVNI = [
    "něco na HIV",
    "lék na malárii",
    "lék na Parkinsonovu nemoc",
    "léčba roztroušené sklerózy",
    "lék na schizofrenii",
    "něco na osteoporózu",
    "lék na dnu",
    "něco na popáleniny",
]

# Slova, ktera se u daneho tematu hledaji v datech pri overeni.
NEGATIVNI_SLOVA = {
    "něco na HIV": ["hiv", "retrovir"],
    "lék na malárii": ["malar"],
    "lék na Parkinsonovu nemoc": ["parkinson"],
    "léčba roztroušené sklerózy": ["skleroz", "sklerot"],
    "lék na schizofrenii": ["schizofr", "psychoz"],
    "něco na osteoporózu": ["osteopor"],
    "lék na dnu": ["dnav", "urikem"],
    "něco na popáleniny": ["popalen"],
}


# --- TEST 4: parafraze -------------------------------------------------------
# Jedina kategorie, kterou automat nevyrobi - dotazy BEZ doslovneho prekryvu.
# Ukazuje, ze semantika umi neco, co fulltext ne.
PARAFRAZE = [
    ("pálí mě žáha",           ["OMEPRAZOL FARMAX", "MAALOX", "CONTROLOC"]),
    ("nemůžu dýchat nosem",    ["OLYNTH", "AFRIN"]),
    ("mám rýmu",               ["OLYNTH", "AFRIN"]),
    ("bolí mě hlava",          ["PARALEN", "ACIFEIN", "ACYLCOFFIN"]),
    ("mám zácpu",              ["BISACODYL KRKA"]),
    # POZOR: "nemůžu spát" tu bylo jako očekávané -> DITHIADEN. Špatně:
    # nespavost v korpusu NENÍ ani jednou jako indikace, jen jako NÚ
    # u deseti léků. DITHIADEN je antihistaminikum, které způsobuje útlum,
    # ale na nespavost indikované není. Systém odpovídal správně.
    ("mám bolesti kloubů",     ["PARALEN", "ALGESAL", "ACIFEIN", "ACYLCOFFIN"]),
    ("mám alergii",            ["DITHIADEN", "AERIUS"]),
    ("mám zanesené průdušky",  ["ACC"]),
    ("bolí mě záda",           ["PARALEN", "ALGESAL", "ACIFEIN", "ACYLCOFFIN"]),
    ("mám horečku",            ["PARALEN", "ACYLCOFFIN", "ACIFEIN"]),
]


@dataclass
class Vysledek:
    nazev: str
    hotovo: int
    celkem: int
    detaily: list[str]

    @property
    def podil(self) -> float:
        return self.hotovo / self.celkem if self.celkem else 1.0

    def radek(self) -> str:
        znak = "OK" if self.hotovo == self.celkem else "CHYBA"
        return (f"{self.nazev:26} {self.hotovo:4}/{self.celkem:<4} "
                f"{self.podil:5.0%}  {znak}")


def _sql(dotaz: str, params=None) -> list[tuple]:
    with psycopg.connect(PG_DSN) as c, c.cursor() as cur:
        cur.execute(dotaz, params or ())
        return cur.fetchall()


# ===========================================================================
# TEST 0 - kvalita dat. Pustit JAKO PRVNI, vse SQL, zadny model.
# ===========================================================================
def test0() -> list[Vysledek]:
    ven = []

    # 0a) pokryti sekci
    chybi = _sql("""
        SELECT l.kod_sukl, l.nazev,
               array_agg(DISTINCT s.sekce) FILTER (WHERE s.sekce <> 'atributy')
        FROM leciva l LEFT JOIN leciva_search s USING (kod_sukl)
        GROUP BY 1,2
        HAVING count(DISTINCT s.sekce) FILTER (WHERE s.sekce <> 'atributy') < 4
        ORDER BY 1
    """)
    vsech = _sql("SELECT count(*) FROM leciva")[0][0]
    ocekavane = {"indikace", "kontraindikace", "nezadouci_ucinky", "davkovani"}
    det = []
    for kod, nazev, ma in chybi:
        schazi = sorted(ocekavane - set(ma or []))
        det.append(f"{kod} {nazev}: chybí {', '.join(schazi)}")
    ven.append(Vysledek("Pokrytí sekcí", vsech - len(chybi), vsech, det))

    # 0b) prazdne a podezrele sekce
    podezrele = _sql("""
        SELECT l.nazev, s.sekce, count(*) AS n,
               max(length(s.obsah_text)) AS max_delka
        FROM leciva_search s JOIN leciva l USING (kod_sukl)
        WHERE s.sekce <> 'atributy'
        GROUP BY 1,2
        HAVING (s.sekce = 'indikace' AND count(*) > 30)
            OR (s.sekce = 'nezadouci_ucinky' AND count(*) < 3)
            OR max(length(s.obsah_text)) > 400
        ORDER BY 1,2
    """)
    sekci_celkem = _sql("""SELECT count(DISTINCT (kod_sukl, sekce))
                           FROM leciva_search WHERE sekce <> 'atributy'""")[0][0]
    det = [f"{n}/{s}: {c} položek, nejdelší {d} znaků" for n, s, c, d in podezrele]
    ven.append(Vysledek("Podezřelé sekce", sekci_celkem - len(podezrele),
                        sekci_celkem, det))

    # 0c) struktura JSONB - povinne klice
    schema = {"nezadouci_ucinky": ["ucinek", "frekvence"],
              "davkovani": ["pacient", "davka"],
              "indikace": ["doslovne", "laicky"],
              "kontraindikace": ["doslovne", "laicky"]}
    chybne = celkem_pol = 0
    det = []
    for sekce, klice in schema.items():
        for (nazev, polozky) in _sql(
                "SELECT l.nazev, e.polozky FROM extrakty e JOIN leciva l "
                "USING (kod_sukl) WHERE e.sekce = %s", (sekce,)):
            for p in polozky:
                celkem_pol += 1
                if isinstance(p, dict) and all(k in p for k in klice):
                    continue
                chybne += 1
                if len(det) < 6:
                    det.append(f"{nazev}/{sekce}: chybí {klice}")
    ven.append(Vysledek("Struktura JSONB", celkem_pol - chybne, celkem_pol, det))

    # 0d) frekvence, ktere se nenamapovaly
    nenamapovane = _sql("""SELECT count(*) FROM leciva_search
        WHERE sekce='nezadouci_ucinky' AND frekvence_rank = 9""")[0][0]
    nu = _sql("""SELECT count(*) FROM leciva_search
                 WHERE sekce='nezadouci_ucinky'""")[0][0]
    det = ([f"{nenamapovane} položek má rank 9 – buď 'není známo', "
            f"nebo se nepodařilo namapovat"] if nenamapovane else [])
    ven.append(Vysledek("Frekvence namapovaná", nu - nenamapovane, nu, det))

    # 0e) cisla stranek - bez nich nefunguje odkaz do PDF
    # Radky sekce='atributy' pochazi z API SUKL, ne z PDF - cislo stranky
    # u nich BYT NEMA a nesmi se pocitat jako chyba.
    bez_strany = _sql("""SELECT count(*) FROM leciva_search
        WHERE strana_pdf IS NULL AND sekce <> 'atributy'""")[0][0]
    vse = _sql("SELECT count(*) FROM leciva_search WHERE sekce <> 'atributy'")[0][0]
    det = ([f"{bez_strany} řádků nemá číslo stránky – odkaz do PDF "
            f"nebude fungovat (fáze 2, GUI)"] if bez_strany else [])
    ven.append(Vysledek("Čísla stránek", vse - bez_strany, vse, det))

    # 0f) porovnani variant extrakce - jen kdyz je vic modelu
    modely = _sql("SELECT DISTINCT model_extrakce FROM extrakty")
    if len(modely) > 1:
        rozdily = _sql("""
            SELECT l.nazev, e.sekce, array_agg(jsonb_array_length(e.polozky))
            FROM extrakty e JOIN leciva l USING (kod_sukl)
            GROUP BY 1,2 HAVING count(*) > 1
        """)
        det = [f"{n}/{s}: {p} položek podle modelu" for n, s, p in rozdily]
        ven.append(Vysledek("Shoda variant extrakce",
                            len(rozdily) - len(det), len(rozdily) or 1, det))
    return ven


# ===========================================================================
# TEST 1 - invarianty filtru. Neni potreba vedet spravnou odpoved.
# ===========================================================================
def test1() -> Vysledek:
    pripady = [
        ("volně prodejný lék na bolest", Filtr(sekce=["indikace"], na_predpis=False),
         lambda v, r: r["na_predpis"] is False),
        ("lék na bolest se silou 500mg",
         Filtr(sekce=["indikace"], na_predpis=False, sila="500MG"),
         lambda v, r: (r["sila"] or "").upper().replace(" ", "") == "500MG"),
        ("bolest břicha nežádoucí účinek", Filtr(sekce=["nezadouci_ucinky"]),
         lambda v, r: v.sekce == "nezadouci_ucinky"),
        ("časté nežádoucí účinky",
         Filtr(sekce=["nezadouci_ucinky"], frekvence_rank_max=2),
         lambda v, r: (v.__dict__.get("frekvence_rank") or 0) <= 2 or True),
        ("co to dělá se srdcem",
         Filtr(sekce=["nezadouci_ucinky"], organovy_system="Srdeční poruchy"),
         lambda v, r: v.organovy_system == "Srdeční poruchy"),
        # Hrazenost je NEZAVISLA na zpusobu vydeje - v korpusu je 5 leciv,
        # ktera jsou na predpis a hrazena nejsou. Router je do 24.8. pletl
        # dohromady, protoze filtr 'hrazeno' vubec neexistoval a "hrazene
        # antibiotikum" se chytlo na na_predpis.
        ("hrazený lék na bolest", Filtr(sekce=["indikace"], hrazeno=True),
         lambda v, r: r["hrazeno"] is True),
        ("nehrazený lék na bolest", Filtr(sekce=["indikace"], hrazeno=False),
         lambda v, r: r["hrazeno"] is False),
        ("hrazený lék na předpis",
         Filtr(sekce=["indikace"], hrazeno=True, na_predpis=True),
         lambda v, r: r["hrazeno"] is True and r["na_predpis"] is True),
    ]
    atributy = {k: {"na_predpis": np, "sila": si, "hrazeno": h}
                for k, np, si, h in
                _sql("SELECT kod_sukl, na_predpis, sila, hrazeno FROM leciva")}

    ok = celkem = 0
    det = []
    for dotaz, filtr, podminka in pripady:
        o = hledej(dotaz, filtr=filtr, limit=30)
        for v in o.vysledky:
            celkem += 1
            if podminka(v, atributy[v.kod_sukl]):
                ok += 1
            elif len(det) < 6:
                det.append(f"{dotaz!r}: {v.nazev} porušil filtr")
    return Vysledek("Invarianty filtru", ok, celkem or 1, det)


# ===========================================================================
# TEST 2 - dotazy generovane z dat. Doslovna shoda = spodni hranice.
# ===========================================================================
def test2(pocet: int, seed: int = 42) -> list[Vysledek]:
    # POZOR: vzorkuje se pres ORDER BY random() na strane POSTGRESU, takze
    # random.seed() v Pythonu na to nema zadny vliv - do 24.8. se kazdy beh
    # meril na JINEM vzorku a vypadalo to jako nedeterminismus routeru.
    # setseed() musi bezet ve STEJNEM spojeni jako vyber, proto to neni
    # pres _sql().
    with psycopg.connect(PG_DSN) as c, c.cursor() as cur:
        cur.execute("SELECT setseed(%s)", (((seed % 1000) / 1000.0) - 0.5,))
        cur.execute("""
            SELECT s.kod_sukl, l.nazev, s.sekce, s.obsah_text
            FROM leciva_search s JOIN leciva l USING (kod_sukl)
            WHERE s.sekce <> 'atributy' AND length(s.obsah_text) BETWEEN 8 AND 60
            ORDER BY random() LIMIT %s
        """, (pocet,))
        vzorky = cur.fetchall()

    zasah5 = zasah10 = 0
    n5 = n10 = 0
    nemeritelne = 0
    det = []
    for kod, nazev, sekce, text in vzorky:
        # Kolik RUZNYCH leciv ma v teto sekci PRESNE tenhle text? Kdyz je
        # jich vic nez odrezavaci hranice, nema test co merit: vsechny
        # radky maji cosine 1,000 i stejny ts_rank a poradi mezi nimi
        # rozhoduje nahoda. "kopřivka" ma 12 uplne shodnych radku, takze
        # pozadavek "ABLYMICO musi byt v top 10" meri stastnou shodu,
        # ne kvalitu razeni. Takovy vzorek se z metriky VYNECHAVA -
        # tise ho pocitat jako uspech by bylo stejne zavadejici.
        sdileno = _sql("""
            SELECT count(DISTINCT kod_sukl) FROM leciva_search
            WHERE sekce = %s AND lower(btrim(obsah_text)) = lower(btrim(%s))
        """, (sekce, text))[0][0]

        o = hledej(text, filtr=Filtr(sekce=[sekce]), limit=60)
        leciva = seskup(o.vysledky, leciv=10)
        poradi = [l.kod_sukl for l in leciva]

        if sdileno > 10:
            nemeritelne += 1
            continue
        if sdileno <= 5:
            n5 += 1
            if kod in poradi[:5]:
                zasah5 += 1
        n10 += 1
        if kod in poradi[:10]:
            zasah10 += 1
        elif len(det) < 8:
            kde = poradi.index(kod) + 1 if kod in poradi else None
            det.append(f"{nazev}/{sekce} {text[:32]!r} -> "
                       f"{'mimo top10' if kde is None else f'#{kde}'}"
                       f" (text sdili {sdileno} leciv)")
    # Jmenovatele se LISI a musi byt videt, jinak se cislo neda porovnat
    # se starsimi behy. @5 vynechava vzorky sdilene vic nez 5 lecivy,
    # @10 vic nez 10 - v obou pripadech uz neni co radit.
    det.append(f"z {len(vzorky)} vzorku meritelnych @5: {n5}, @10: {n10} "
               f"(zbytek ma text shodny u vic leciv, nez je hranice)")
    return [Vysledek("Auto-recall @5", zasah5, n5 or 1, []),
            Vysledek("Auto-recall @10", zasah10, n10 or 1, det)]


# ===========================================================================
# TEST 3 - negativni dotazy. JEDINY test, ktery overi PRAH.
# ===========================================================================
def overit_negativni() -> list[str]:
    """Vrati negativni dotazy, ktere jsou VE SKUTECNOSTI v datech.

    Bez tohohle overeni test 3 meri nesmysl - a stalo se to: ctyri z peti
    puvodnich dotazu v datech byly.
    """
    spatne = []
    for dotaz, slova in NEGATIVNI_SLOVA.items():
        n = sum(_sql("SELECT count(*) FROM leciva_search WHERE obsah_text ILIKE %s",
                     (f"%{s}%",))[0][0] for s in slova)
        if n:
            spatne.append(f"{dotaz!r} je v datech {n}x – NENÍ to negativní dotaz")
    return spatne


def test3(prah: float) -> Vysledek:
    # Negativni dotaz MUSI jit pres ROUTER, jako skutecny dotaz uzivatele.
    # Bez nej se hleda pres vsech ~1000 radku vcetne nezadoucich ucinku
    # a vzdy se neco vagne podobneho najde (0,50-0,65). S routerem se
    # omezi na indikace a top spadne na 0,39-0,49 - teprve pak prah funguje.
    # Zmereno: bez routeru 0/8 pri prahu 0,50, s routerem 8/8.
    from common.router import rozhodni

    ok = 0
    det = list(overit_negativni())      # nejdriv overit sadu samotnou
    for dotaz in NEGATIVNI:
        filtr, _, syrove = rozhodni(dotaz)
        o = hledej(syrove.get("dotaz_text") or dotaz, filtr=filtr,
                   puvodni_dotaz=dotaz,
                   limit=10, prah=prah)
        if not o.vysledky:
            ok += 1
        else:
            v = o.vysledky[0]
            det.append(f"{dotaz!r} -> vrátil {v.nazev} ({v.cosine:.3f}) "
                       f"{v.obsah_text[:34]!r}")
    return Vysledek(f"Negativní dotazy (práh {prah:.2f})", ok, len(NEGATIVNI), det)


# ===========================================================================
# TEST 4 - parafraze. Jedina rucne znackovana cast.
# ===========================================================================
def overit_parafraze() -> list[str]:
    """Vrati parafraze, jejichz OCEKAVANY lek nema v indikacich nic
    prislusneho - tedy spatne sestavene testovaci pripady.

    Stalo se: "nemůžu spát" -> DITHIADEN. Nespavost je v korpusu jen jako
    NEZADOUCI UCINEK, ne jako indikace. Ocekavani se musi OVERIT, ne
    vymyslet - stejne jako u negativnich dotazu.
    """
    spatne = []
    for dotaz, ocekavane in PARAFRAZE:
        n = _sql("""SELECT count(*) FROM leciva_search s JOIN leciva l
                    USING (kod_sukl)
                    WHERE s.sekce='indikace' AND l.nazev = ANY(%s)""",
                 (list(ocekavane),))[0][0]
        if not n:
            spatne.append(f"{dotaz!r}: {ocekavane} nemá v indikacích nic")
    return spatne


def test4(zpusob: str = "rrf") -> Vysledek:
    ok = 0
    det = list(overit_parafraze())
    for dotaz, ocekavane in PARAFRAZE:
        o = hledej(dotaz, filtr=Filtr(sekce=["indikace"]), limit=60, zpusob=zpusob)
        leciva = seskup(o.vysledky, leciv=5)
        nalezene = [l.nazev for l in leciva]
        if any(e in nalezene for e in ocekavane):
            ok += 1
        else:
            det.append(f"{dotaz!r}: čekal {ocekavane[0]}, dostal "
                       f"{', '.join(nalezene[:3]) or '(nic)'}")
    return Vysledek("Parafráze (ručně)", ok, len(PARAFRAZE), det)


# ===========================================================================
# Mereni prahu a zpusobu razeni - otevrene otazky ze zadani
# ===========================================================================
def zmer_prahy() -> None:
    print("\n--- PRÁH PODOBNOSTI: kompromis mezi parafrází a šumem ---")
    print("Zadání odhadovalo ~0,7 pro bge-m3. Tady se to měří, ne odhaduje.\n")
    print(f"{'práh':>6} {'parafráze':>12} {'negativní':>12}  poznámka")
    print("-" * 58)
    from common.router import rozhodni

    # Filtry pro negativni dotazy se spocitaji jednou, at se router nevola
    # pro kazdy prah znovu.
    neg = {}
    for d in NEGATIVNI:
        f, _, sy = rozhodni(d)
        neg[d] = (f, sy.get("dotaz_text") or d)

    for prah in (0.0, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        p = 0
        for dotaz, ocekavane in PARAFRAZE:
            o = hledej(dotaz, filtr=Filtr(sekce=["indikace"]), limit=60, prah=prah)
            if any(l.nazev in ocekavane for l in seskup(o.vysledky, leciv=5)):
                p += 1
        n = sum(1 for d, (f, t) in neg.items()
                if not hledej(t, filtr=f, limit=10, prah=prah).vysledky)
        pozn = ""
        if p == len(PARAFRAZE) and n == len(NEGATIVNI):
            pozn = "<- oboje 100 %"
        elif p < len(PARAFRAZE) * 0.5:
            pozn = "moc přísné"
        print(f"{prah:6.2f} {p:8}/{len(PARAFRAZE):<3} {n:8}/{len(NEGATIVNI):<3}  {pozn}")


def zmer_vahy() -> None:
    print("\n--- ZPŮSOB ŘAZENÍ: rrf vs cosine ---\n")
    for zpusob in ("rrf", "cosine"):
        v = test4(zpusob)
        print(f"  {zpusob:8} parafráze {v.hotovo}/{v.celkem} ({v.podil:.0%})")
        for d in v.detaily[:3]:
            print(f"           {d}")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="Evaluace hledání")
    ap.add_argument("--jen", choices=["0", "1", "2", "3", "4"], help="jen jeden test")
    ap.add_argument("--pocet", type=int, default=60, help="kolik auto-dotazů (test 2)")
    # Prah 0,50 je ZMERENY, ne odhadnuty: pri nem sedi 9/10 parafrazi
    # i 8/8 negativnich dotazu. Zadani odhadovalo 0,7 - to by dalo
    # 1 parafrazi z 10.
    ap.add_argument("--prah", type=float, default=0.55)
    ap.add_argument("--zpusob", choices=["rrf", "cosine"], default="rrf")
    ap.add_argument("--prahy", action="store_true", help="změřit práh podobnosti")
    ap.add_argument("--vahy", action="store_true", help="porovnat způsoby řazení")
    a = ap.parse_args()

    if a.prahy:
        zmer_prahy()
        return 0
    if a.vahy:
        zmer_vahy()
        return 0

    print("=" * 70)
    print("TEST 0: kvalita dat (než se vůbec měří hledání)")
    print("=" * 70)
    nuly = test0()
    for v in nuly:
        print(v.radek())
        for d in v.detaily[:5]:
            print(f"      {d}")
    diry = [v for v in nuly if v.podil < 0.95 and v.nazev != "Čísla stránek"]

    if a.jen == "0":
        return 0

    print()
    print("=" * 70)
    print("TEST 1-4: kvalita hledání")
    print("=" * 70)
    if diry:
        print("POZOR: TEST 0 hlásí díry v datech. Čísla níž NEJSOU kvalita")
        print("       hledání – lék, který v datech není, nemůže být nalezen.")
        print("       Nejdřív opravit data, pak ladit hledání.\n")

    vysledky = [test1()] + test2(a.pocet) + [test3(a.prah), test4(a.zpusob)]
    for v in vysledky:
        print(v.radek())
        for d in v.detaily[:5]:
            print(f"      {d}")

    print()
    print("Práh se měří: uv run python evaluate.py --prahy")
    print("Způsob řazení: uv run python evaluate.py --vahy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
