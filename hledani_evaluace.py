#!/usr/bin/env python3
"""Evaluace hledani nad celym korpusem (5 880 SPC) - jak poznat, ze to funguje.

Tri casti:
  TEST 0   kvalita dat v DB (jen SQL, bez modelu) - pustit jako prvni.
           Kdyz hlasi diry, cisla hledani niz nejsou kvalita hledani:
           lek, ktery v datech neni, nemuze byt nalezen.
  PARAFRAZE PODLE ATC  dotaz laika ("pálí mě žáha") -> je v top 5 lek ze
           spravne terapeuticke skupiny? ATC je z registru SUKL, ne
           z modelu, takze test nezavisi na extrakci.
  NEGATIVNI  dotazy mimo medicinu pres router - nesmi prijit nic
           (overuje prah + router).

Pustit po KAZDE zmene promptu, modelu, chunkovani, vah nebo prahu.
Router neni deterministicky - presnost kolisa o +-4 body mezi behy.

Do 6. 10. 2026 tu byly i testy 1-4 nad puvodnimi 32 leky (invarianty
filtru, auto-recall, negativni temata, parafraze s nazvem leku). Na celem
trhu nefungovaly ("negativni" temata v trhu jsou, parafraze cekaly
konkretni nazev) a byly smazany; jsou v gitu do commitu 71c761c.

Pouziti:
  uv run python hledani_evaluace.py                  # vse (test 0 + parafraze + negativni)
  uv run python hledani_evaluace.py --jen-data       # jen test 0 (rychle, bez modelu)
  uv run python hledani_evaluace.py --prahy          # parafraze a negativni pro ruzne prahy
  uv run python hledani_evaluace.py --vahy           # porovnat zpusoby razeni (rrf / cosine)
"""

import io
import sys
import argparse
from dataclasses import dataclass

import psycopg

from common.config import PG_DSN
from common.hledani import Filtr, hledej, seskup

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
        WHERE l.zastupce AND l.spc IS NOT NULL
        GROUP BY 1,2
        HAVING count(DISTINCT s.sekce) FILTER (WHERE s.sekce <> 'atributy') < 4
        ORDER BY 1
    """)
    # Sekce se nahravaji jen jednou za SPC, u ZASTUPCE (nejmensi kod).
    # Pocitat pres vsechny kody davalo 64 % a vypadalo to jako dira v datech.
    vsech = _sql("SELECT count(*) FROM leciva WHERE zastupce AND spc IS NOT NULL")[0][0]
    ocekavane = {"indikace", "kontraindikace", "nezadouci_ucinky", "davkovani"}
    det = []
    for kod, nazev, ma in chybi:
        schazi = sorted(ocekavane - set(ma or []))
        det.append(f"{kod} {nazev}: chybí {', '.join(schazi)}")
    ven.append(Vysledek("Pokrytí sekcí (po SPC)", vsech - len(chybi), vsech, det))

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

    # 0f) duplicitni radky a rozpor v klicich (pridano 22.9.2026)
    #
    # POZOR NA TO, CO RADEK ROZLISUJE. Radky se shodnym `obsah_text`
    # duplicity byt NEMUSI - lisit se mohou jeste:
    #   - skupinou pacientu: ACC ma 9 indikaci x 3 vekove skupiny = 27 radku
    #   - frekvenci:         ADVANTAN ma tyz ucinek jako 'vzacne' i 'mene caste'
    #   - organovym systemem: ACIFEIN ma "nevolnost" jako 'caste' u traveni
    #                         a 'velmi vzacne' u imunity
    # Merit duplicitu jen pres text je proto past - prvni mereni takhle
    # nahlasilo 19 duplicitnich indikaci, a zadna z nich duplicita nebyla.
    dupl = _sql("""
        SELECT count(*) - count(DISTINCT (kod_sukl, sekce, obsah_text,
               coalesce(sekce_atributy->>'skupina_kod','-'),
               coalesce(frekvence,'-'), coalesce(organovy_system,'-')))
        FROM leciva_search WHERE sekce <> 'atributy'""")[0][0]
    vsech_r = _sql("SELECT count(*) FROM leciva_search WHERE sekce<>'atributy'")[0][0]
    det = ([f"{dupl} řádků je úplná duplicita – zabírají místa ve výsledcích"]
           if dupl else [])
    ven.append(Vysledek("Bez duplicitních řádků", vsech_r - dupl, vsech_r, det))

    # Tyz zdrojovy text musi mit VSUDE tyz klic. Generovani klice je
    # nedeterministicke, takze tataz indikace ve trech vekovych skupinach
    # dostala tri RUZNE klice - a tim tri ruzne vektory, na ktere se tyz
    # dotaz chytal ruzne. Sjednocoval `ocisti_json.py` (jen stary korpus, nerealizovane_kontroly/).
    rozpor = _sql("""
        SELECT count(*) FROM (
            SELECT kod_sukl, sekce, obsah_text FROM leciva_search
            GROUP BY 1,2,3 HAVING count(DISTINCT coalesce(klic,'')) > 1) q""")[0][0]
    skupin = _sql("""SELECT count(*) FROM (SELECT 1 FROM leciva_search
                     WHERE sekce<>'atributy' GROUP BY kod_sukl, sekce,
                     obsah_text) q""")[0][0]
    det = ([f"{rozpor} textů má víc různých klíčů – sjednocení klíčů nad korpusem není hotové (nerealizovane_kontroly/)"]
           if rozpor else [])
    ven.append(Vysledek("Jednotný klíč u téhož textu", skupin - rozpor, skupin, det))

    # 0g) porovnani variant extrakce - jen kdyz je vic modelu
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
# HLEDANI - parafraze podle ATC a negativni dotazy
# ===========================================================================
# Ocekava se TERAPEUTICKA SKUPINA (ATC prefix prideleny SUKLem), ne nazev
# leku: mezi tisici leku muze spravne vyjit jiny omeprazol, nez ktery by
# test jmenoval. ATC je z registru, ne z modelu - test nezavisi na extrakci.
#
# POZOR pri pridavani pripadu: OVERIT PROTI DATUM, ne odhadnout. Stalo se
# trikrat, ze "negativni" dotaz v datech byl a system odpovidal spravne.

# (dotaz laika, ATC prefixy, ktere na nej odpovidaji)
PARAFRAZE_KORPUS = [
    ("pálí mě žáha",                  ["A02"]),
    ("nemůžu dýchat nosem",           ["R01"]),
    ("mám rýmu",                      ["R01", "R06"]),
    ("bolí mě hlava",                 ["N02", "M01"]),
    ("mám horečku",                   ["N02", "M01"]),
    ("bolí mě klouby",                ["M01", "M02", "N02", "M04"]),
    ("mám zácpu",                     ["A06"]),
    ("mám průjem",                    ["A07"]),
    ("mám alergii",                   ["R06", "D07", "S01G"]),
    ("kašlu a nejde mi vykašlat hlen", ["R05"]),
    ("bolí mě v krku",                ["R02"]),
    ("nemůžu spát",                   ["N05C", "N05B", "N05CH"]),
    ("mám vysoký tlak",               ["C02", "C03", "C07", "C08", "C09"]),
    ("mám cukrovku",                  ["A10"]),
    ("mám vysoký cholesterol",        ["C10"]),
    ("mám plíseň na nohou",           ["D01"]),
    ("mám opar na rtu",               ["D06B", "J05"]),
    ("pálí mě při močení",            ["J01", "G04"]),
    ("mám úzkosti",                   ["N05B", "N06A", "N05C"]),
    ("mám depresi",                   ["N06A"]),
]

# Dotazy MIMO medicinu - na ty nesmi prijit nic (overuje prah + router).
NEGATIVNI_KORPUS = [
    "recept na svíčkovou",
    "jak vyměnit pneumatiku",
    "kurz eura dnes",
    "jízdní řád vlaků do Brna",
    "výsledky fotbalové ligy",
    "jak naladit kytaru",
]


def test_parafraze(prah: float, top: int = 5, zpusob: str = "rrf") -> Vysledek:
    """Parafraze podle ATC: je v top N leku aspon jeden ze spravne skupiny?
    Detail: presnost = kolik z top N do skupiny patri."""
    ok = 0
    presnost = []
    det = []
    for dotaz, atc in PARAFRAZE_KORPUS:
        o = hledej(dotaz, filtr=Filtr(sekce=["indikace"]), limit=100, prah=prah,
                   zpusob=zpusob)
        leky = seskup(o.vysledky, leciv=top)
        trefy = [l for l in leky if any((l.nejlepsi.atc or "").startswith(a) for a in atc)]
        presnost.append(len(trefy) / top)
        if trefy:
            ok += 1
        spatne = [f"{l.nazev} ({l.nejlepsi.atc})" for l in leky if l not in trefy]
        det.append(f"{dotaz!r:36} {len(trefy)}/{top} v {'/'.join(atc)}"
                   + (f"   mimo: {', '.join(spatne[:3])}" if spatne else ""))
    det.insert(0, f"průměrná přesnost top {top}: {sum(presnost) / len(presnost):.0%}")
    return Vysledek(f"Parafráze ATC (top {top})", ok, len(PARAFRAZE_KORPUS), det)


def test_negativni(prah: float, router: str | None = None) -> Vysledek:
    """Negativni dotazy mimo medicinu - jdou pres ROUTER jako skutecny dotaz."""
    from common.router import rozhodni
    ok = 0
    det = []
    kw = {"model": router} if router else {}
    for dotaz in NEGATIVNI_KORPUS:
        filtr, _, syrove = rozhodni(dotaz, **kw)
        o = hledej(syrove.get("dotaz_text") or dotaz, filtr=filtr,
                   puvodni_dotaz=dotaz, limit=10, prah=prah)
        if not o.vysledky:
            ok += 1
        else:
            v = o.vysledky[0]
            det.append(f"{dotaz!r} -> {v.nazev} ({v.cosine:.3f}) {v.obsah_text[:40]!r}")
    return Vysledek(f"Negativní mimo medicínu ({prah:.2f})", ok, len(NEGATIVNI_KORPUS), det)


# ===========================================================================
# Mereni prahu a zpusobu razeni
# ===========================================================================
def zmer_prahy() -> None:
    """Parafraze a negativni dotazy pro radu prahu. Prah 0,60 je zmereny na
    32 lecich - na celem trhu pousti falesne shody (todo: premerit)."""
    from common.router import rozhodni

    print("\n--- PRÁH PODOBNOSTI: kompromis mezi parafrází a šumem ---\n")
    print(f"{'práh':>6} {'parafráze':>10} {'přesnost':>9} {'negativní':>10}")
    print("-" * 42)
    # Router se pro negativni dotazy vola JEDNOU, ne pro kazdy prah znovu.
    neg = {}
    for d in NEGATIVNI_KORPUS:
        f, _, sy = rozhodni(d)
        neg[d] = (f, sy.get("dotaz_text") or d)
    for prah in (0.0, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75):
        v = test_parafraze(prah)
        n = sum(1 for d, (f, t) in neg.items()
                if not hledej(t, filtr=f, limit=10, prah=prah, puvodni_dotaz=d).vysledky)
        print(f"{prah:6.2f} {v.hotovo:6}/{v.celkem:<3} {v.detaily[0].split(': ')[1]:>9} "
              f"{n:6}/{len(NEGATIVNI_KORPUS):<3}")


def zmer_vahy(prah: float) -> None:
    print("\n--- ZPŮSOB ŘAZENÍ: rrf vs cosine ---\n")
    for zpusob in ("rrf", "cosine"):
        v = test_parafraze(prah, zpusob=zpusob)
        print(f"  {zpusob:8} parafráze {v.hotovo}/{v.celkem} ({v.podil:.0%}), {v.detaily[0]}")


def main() -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="Evaluace hledání nad celým korpusem")
    ap.add_argument("--jen-data", action="store_true", help="jen test 0 (bez modelu)")
    ap.add_argument("--prah", type=float, default=0.60)
    ap.add_argument("--prahy", action="store_true", help="změřit práh podobnosti")
    ap.add_argument("--vahy", action="store_true", help="porovnat způsoby řazení")
    ap.add_argument("--router", help="jiný model routeru pro negativní dotazy "
                                     "(výchozí config.MODEL_ROUTER)")
    ap.add_argument("--korpus", action="store_true",
                    help="nic nedělá – korpus je od 6. 10. 2026 jediný režim "
                         "(ponecháno kvůli starým návodům)")
    a = ap.parse_args()

    if a.prahy:
        zmer_prahy()
        return 0
    if a.vahy:
        zmer_vahy(a.prah)
        return 0

    print("=" * 70)
    print("TEST 0: kvalita dat (než se vůbec měří hledání)")
    print("=" * 70)
    for v in test0():
        print(v.radek())
        for d in v.detaily[:5]:
            print(f"      {d}")
    if a.jen_data:
        return 0

    print()
    print("=" * 70)
    print("HLEDÁNÍ: parafráze podle ATC + negativní mimo medicínu")
    print("=" * 70)
    for v in (test_parafraze(a.prah), test_negativni(a.prah, a.router)):
        print(v.radek())
        for d in v.detaily:
            print(f"      {d}")
    print()
    print("Práh se měří: uv run python hledani_evaluace.py --prahy")
    print("Způsob řazení: uv run python hledani_evaluace.py --vahy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
