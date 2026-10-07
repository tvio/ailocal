"""Ciselnik pro ROZSIRENI DOTAZU: laicky vyraz -> formulace v textu.

Uloziste je tabulka `slovnik_dotazu` v DB (od 6. 10. 2026, upravuje se
z GUI pres /api/slovnik); `slovnik_dotazu.json` je jen jeji vychozi napln.

Proc existuje vedle slovnik_pojmu.json:

    slovnik_pojmu   odborny termin -> laicky tvar     (pro ZOBRAZENI)
    slovnik_dotazu  vyraz uzivatele -> co je v textu  (pro HLEDANI)

Zmereno 24.8.2026 na MAALOXu, ktery ma reflux popsany opisem a slovo
"reflux" v nem nepadne ani jednou:

    hledat "mám reflux"                                 -> #19 (0,474)
    hledat "regurgitace"        (odborne synonymum)     -> #10 (0,488)
    hledat "vracení kyselého obsahu ze žaludku do úst"  -> #1  (0,647)

Nejlepsi "synonymum" tedy NENI odborny termin, ale FORMULACE Z DOKUMENTU.
Vektor porovnava s tim, co v dokumentu opravdu stoji.

DULEZITE - rozsireni se deje na DOTAZU, ne na datech. Do textu leciva se
NIC nepridava, takze:
  - nevymysli se zadny udaj, ktery neni v SPC
  - uzivatel dal vidi vetu z dokumentu vcetne odkazu na stranu
Kdyby se misto toho generovaly nove radky indikaci, prisli bychom
o dohledatelnost, coz je hlavni prednost cele ukazky.
"""

import json
import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

# Datove soubory lezi vedle modulu (common/data/), ne v koreni projektu -
# cesta tak nezavisi na tom, odkud se skript pousti.
DATA = Path(__file__).parent / "data"
CESTA = DATA / "slovnik_dotazu.json"     # jen VYCHOZI NAPLN tabulky, viz niz

# ---------------------------------------------------------------------------
# Uloziste: tabulka slovnik_dotazu v Postgresu (6. 10. 2026)
# ---------------------------------------------------------------------------
# Do 6. 10. se cetl soubor a drzel se v pameti procesu. Od chvile, kdy jde
# slovnik menit z GUI, to nestaci: zmenu videl jen proces, ktery ji prijal
# (dva Sparky / vic workeru), a nasazeni noveho obrazu by soubor prepsalo.
#
# Tabulka je spolecna vsem instancim a cte se pri KAZDEM dotazu - jeden maly
# select (desitky radku) proti 1,5 s routeru. Zadna cache, zadny restart.
#
# slovnik_dotazu.json zustava v gitu jako vychozi napln: nahraje se JEN
# kdyz tabulka jeste neexistuje. Pozdejsi upravy souboru se do DB nedostanou.
#
# POZOR: extrakce_4_db.py (--korpus, --znovu) tuhle tabulku mazat NESMI - jsou
# v ni zaznamy pridane uzivateli. Nema cizi klic na leciva, takze
# TRUNCATE leciva CASCADE se ji netyka.
DDL = """
CREATE TABLE IF NOT EXISTS slovnik_dotazu (
    id          BIGSERIAL PRIMARY KEY,
    vyraz       TEXT NOT NULL,          -- kmen toho, co pise uzivatel, malymi
    formulace   TEXT NOT NULL,          -- formulace, ktera je v datech
    poradi      INTEGER NOT NULL,       -- poradi formulaci u vyrazu (mensi = driv)
    zdroj       TEXT NOT NULL DEFAULT 'gui',   -- 'vychozi' (ze souboru) | 'gui'
    vytvoreno   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (vyraz, formulace)
);
"""
MAX_FORMULACI = 4          # rozsir() bere nejvys 4 varianty na dotaz
_ZAMEK = 7310061           # advisory lock: zalozeni tabulky a zapis po jednom

_tabulka_overena: set[str] = set()      # DSN, kde uz tabulka urcite je


class ChybaSlovniku(ValueError):
    """Zaznam nejde pridat / odebrat. `kod` rika proc (pro HTTP stav)."""

    def __init__(self, kod: str, zprava: str):
        super().__init__(zprava)
        self.kod = kod


def _ze_souboru(cesta: Path) -> dict[str, list[str]]:
    if not cesta.exists():
        return {}
    data = json.loads(cesta.read_text(encoding="utf-8"))
    return {str(k).strip().lower(): list(v)
            for k, v in data.items()
            if v and not str(k).startswith("_")}


def _zajisti_tabulku(conn, dsn: str) -> None:
    """Zalozi tabulku a naplni ji ze souboru - jen kdyz jeste neexistuje."""
    if dsn in _tabulka_overena:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_ZAMEK,))
        nova = cur.execute("SELECT to_regclass('slovnik_dotazu') IS NULL").fetchone()[0]
        if nova:
            cur.execute(DDL)
            radky = [(k, f, i) for k, v in _ze_souboru(CESTA).items()
                     for i, f in enumerate(v)]
            cur.executemany("INSERT INTO slovnik_dotazu (vyraz, formulace, poradi, zdroj) "
                            "VALUES (%s, %s, %s, 'vychozi') ON CONFLICT DO NOTHING", radky)
            logger.info("slovnik_dotazu: tabulka zalozena, %d zaznamu z %s", len(radky), CESTA)
    conn.commit()
    _tabulka_overena.add(dsn)


def _pripoj(dsn: str | None):
    import psycopg
    from common.config import PG_DSN
    dsn = dsn or PG_DSN
    conn = psycopg.connect(dsn)
    try:
        _zajisti_tabulku(conn, dsn)
    except Exception:
        conn.close()
        raise
    return conn


def vypis(*, dsn: str | None = None) -> list[tuple[str, list[str]]]:
    """Slovnik pro zobrazeni: naposledy upraveny vyraz PRVNI."""
    with _pripoj(dsn) as conn:
        radky = conn.execute(
            "SELECT vyraz, array_agg(formulace ORDER BY poradi, id) "
            "FROM slovnik_dotazu GROUP BY vyraz ORDER BY max(id) DESC").fetchall()
    return [(v, list(f)) for v, f in radky]


def nacti(cesta: Path | None = None, *, znovu: bool = False,
          dsn: str | None = None) -> dict[str, list[str]]:
    """Slovnik pro hledani. Z DB, pokazde cerstvy.

    `cesta` = cist ze souboru misto DB (testy a mereni nad jinym slovnikem).
    `znovu` zustava jen kvuli starym volanim - cache uz neni.
    """
    if cesta is not None:
        return _ze_souboru(cesta)
    return dict(vypis(dsn=dsn))


def cisti_formulace(formulace: str | list[str]) -> list[str]:
    """Jedna nebo vic formulaci -> seznam bez prazdnych a bez opakovani."""
    ven: list[str] = []
    for f in ([formulace] if isinstance(formulace, str) else formulace):
        f = " ".join(str(f).split())
        if f and f.lower() not in (x.lower() for x in ven):
            ven.append(f)
    return ven


def pridej(vyraz: str, formulace: str | list[str], *, dsn: str | None = None) -> None:
    """Prida k vyrazu jednu nebo VIC formulaci - vsechny, nebo zadnou.

    Nove formulace jdou u vyrazu na PRVNI mista, v poradi, v jakem prisly.
    Neoveruje, ze formulace je v datech - to dela volajici (api.py), ktery
    vi, proti cemu overovat.
    """
    vyraz = " ".join(vyraz.lower().split())
    nove = cisti_formulace(formulace)
    if len("".join(_slova(vyraz))) < 3 or vyraz.startswith("_"):
        raise ChybaSlovniku("neplatne", "Výraz musí mít aspoň 3 písmena.")
    if not nove:
        raise ChybaSlovniku("neplatne", "Vyberte aspoň jednu formulaci.")
    if any(len(f) < 3 for f in nove):
        raise ChybaSlovniku("neplatne", "Formulace musí mít aspoň 3 znaky.")
    with _pripoj(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_ZAMEK,))
        stavajici = cur.execute("SELECT formulace, poradi FROM slovnik_dotazu "
                                "WHERE vyraz = %s", (vyraz,)).fetchall()
        uz_tam = [f for f in nove if f.lower() in (s.lower() for s, _ in stavajici)]
        if uz_tam:
            raise ChybaSlovniku("duplicita", f"U výrazu „{vyraz}“ už je: "
                                + ", ".join(f"„{f}“" for f in uz_tam) + ".")
        if len(stavajici) + len(nove) > MAX_FORMULACI:
            raise ChybaSlovniku(
                "plno", f"Výraz „{vyraz}“ může mít nejvýš {MAX_FORMULACI} formulace "
                f"(víc se při hledání nepoužije). Už má {len(stavajici)}, "
                f"přidáváte {len(nove)}.")
        prvni = min((p for _, p in stavajici), default=len(nove)) - len(nove)
        cur.executemany("INSERT INTO slovnik_dotazu (vyraz, formulace, poradi) "
                        "VALUES (%s, %s, %s)",
                        [(vyraz, f, prvni + i) for i, f in enumerate(nove)])
    logger.info("slovnik_dotazu: pridano %r -> %r", vyraz, nove)


def odeber(vyraz: str, formulace: str, *, dsn: str | None = None) -> None:
    with _pripoj(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM slovnik_dotazu WHERE vyraz = %s AND formulace = %s",
                    (vyraz, formulace))
        if not cur.rowcount:
            raise ChybaSlovniku("neni", "Taková dvojice ve slovníku není.")
    logger.info("slovnik_dotazu: odebrano %r -> %r", vyraz, formulace)


def _bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def _slova(s: str) -> list[str]:
    """Rozpad na slova. Interpunkce se zahazuje, diakritika taky."""
    return re.findall(r"[a-z0-9]+", _bez_diakritiky(s))


def _sedi(klic: str, slova: list[str]) -> bool:
    """Sedi klic slovniku na dotaz? Porovnava se PO SLOVECH, ne podretezcem.

    Do 22.9.2026 tu bylo `if _bez_diakritiky(klic) in d`, tedy hledani
    PODRETEZCE kdekoliv uvnitr textu. To melo dve vady:

      1. Klic se trefil doprostred jineho slova. Zmereno: klic 'tlak'
         se trefil v 'tlak v uchu' i v 'nizky tlak' a pridal k dotazu
         'vysoky krevni tlak' - tedy OPACNY vyznam. (Ten klic je navic
         pryc, viz slovnik - 'vysoky tlak' ho plne nahrazuje.)
      2. Nic to neresilo se sklonovanim, jen to matlo. 'ryma' se
         netrefila v 'rymu', protoze posledni pismeno je jine.

    Ted se dotaz rozpadne na slova a klic sedi, kdyz jeho slova tvori
    PREFIXY po sobe jdoucich slov dotazu. Tim projdou KMENY, na kterych
    slovnik stoji ('kasl' je prefix 'kaslu'), ale uz se netrefi
    doprostred slova.
    """
    kl = _slova(klic)
    if not kl or len(kl) > len(slova):
        return False
    for i in range(len(slova) - len(kl) + 1):
        if all(slova[i + j].startswith(k) for j, k in enumerate(kl)):
            return True
    return False


def rozsir(dotaz: str, *, cesta: Path | None = None, limit: int = 4) -> list[str]:
    """Vrati varianty dotazu VCETNE puvodniho, prvni je vzdy puvodni.

    Klice se hledaji PO SLOVECH, jako prefixy (viz _sedi()) - uzivatel
    napise "mám reflux", klic je "reflux". Delsi klice maji prednost,
    aby "pálení žáhy" prebilo "žáha", kdyby tam bylo oboje.

    Porovnava se BEZ DIAKRITIKY, protoze lide bezne pisou "kaslu" misto
    "kašlu" - a bge-m3 je na diakritiku citlivy (zmereno: "kasel" vraci
    ABAKTAL misto ACC). Klice jsou proto KMENY ("kasl", ne "kašel"), aby
    prosly i skloňovanim. Hodnoty naopak diakritiku MAJI - prave ony ji
    do hledani vrati.
    """
    if not dotaz:
        return []
    slova = _slova(dotaz)
    slovnik = nacti(cesta)
    ven: list[str] = [dotaz]
    for klic in sorted(slovnik, key=len, reverse=True):
        if _sedi(klic, slova):
            for varianta in slovnik[klic]:
                if varianta not in ven:
                    ven.append(varianta)
        if len(ven) > limit:
            break
    return ven[:limit + 1]


# ---------------------------------------------------------------------------
# ATC jako ZACHRANNA SIT
# ---------------------------------------------------------------------------
# Kdyz dotaz nenajde nic nad prahem, da se jeste zkusit terapeuticka
# skupina. ATC prirazuje SUKL, je to RIZENA HODNOTA - neodhaduje se.
#
# POZOR NA HRANICE TOHOHLE NASTROJE:
#   1. Je to znalost NA UROVNI TRIDY, ne leciva. Vsechna leciva ve skupine
#      dostanou tutez znamku, takze to zvedne RECALL, ne precision -
#      uvnitr skupiny se radit neda.
#   2. Je to NASE znalost, ne udaj ze SPC. Proto se vysledky ukazuji
#      ODDELENE a oznacene, nikdy se nemichaji mezi nalezy z dokumentu
#      a nikdy z nich nevznikaji nove radky indikaci. Kdyby vznikaly,
#      prisli bychom o dohledatelnost na stranu SPC, coz je hlavni
#      prednost cele ukazky.

CESTA_ATC = DATA / "atc_mapa.json"

_cache_atc: dict[str, list[str]] | None = None


def nacti_atc(cesta: Path | None = None, *, znovu: bool = False) -> dict[str, list[str]]:
    global _cache_atc
    if _cache_atc is not None and not znovu:
        return _cache_atc
    p = cesta or CESTA_ATC
    if not p.exists():
        _cache_atc = {}
        return _cache_atc
    data = json.loads(p.read_text(encoding="utf-8"))
    _cache_atc = {str(k).strip().upper(): list(v.get("vyrazy", []))
                  for k, v in data.items()
                  if isinstance(v, dict) and not str(k).startswith("_")}
    return _cache_atc


def atc_pro_dotaz(dotaz: str, *, cesta: Path | None = None) -> list[str]:
    """ATC prefixy, ktere by na dotaz mohly sedet. Prazdne = nic nenalezeno."""
    if not dotaz:
        return []
    d = dotaz.lower()
    return [atc for atc, vyrazy in nacti_atc(cesta).items()
            if any(v.lower() in d for v in vyrazy)]
