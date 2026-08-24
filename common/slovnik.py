"""Cislenik pojmu jako AUTORITA pro laicky tvar.

Smer toku dat:

    extrakce  --(nove terminy)-->  postav_slovnik.py  -->  slovnik_pojmu.json
    slovnik_pojmu.json  --(kanonicky tvar)-->  extrakce

Tedy: slovnik z extrakce VZNIKA, ale zaroven ji RIDI. Kdyz je termin ve
slovniku, pouzije se tvar ze slovniku a to, co model vygeneroval, se
zahodi. Kdyz ve slovniku neni, necha se modelu a pri dalsim behu
postav_slovnik.py do slovniku pribude.

Proc takhle:
  - KONZISTENCE. Zmereno, ze bez slovniku mel kazdy paty termin vic
    ruznych laickych tvaru ("pancytopenie" mela sest podob).
  - OPRAVITELNOST. Kdyz je preklad spatne, opravi se JEDNOU ve slovniku
    a projevi se to vsude. Bez toho by se musel opravovat u kazdeho leku.
  - Rucni opravy ve slovniku PREZIJI preextrahovani. To je zasadni -
    jinak by kazdy novy beh prepsal praci cloveka.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CESTA = Path("slovnik_pojmu.json")

# Rucni prepisy. Tenhle soubor se NIKDY negeneruje automaticky a ma vzdy
# prednost pred vygenerovanym slovnikem. Duvod: postav_slovnik.py prestavuje
# slovnik z toho, co je v datech, takze bez tohohle oddeleni by rucni oprava
# prezila jen pri urcitem poradi kroku - a to je past, na kterou se neda
# spolehat. Sem se zapisuje reseni polozek z todo.md.
CESTA_RUCNI = Path("slovnik_rucni.json")

_cache: dict[str, str] | None = None

# Predpony, ktere nejsou soucast terminu. Stejne pravidlo jako v routeru:
# "lecba refluxni ezofagitidy" a "refluxni ezofagitida" je TYZ termin,
# ale jako dva ruzne klice by se slovnik na druhy nikdy netrefil.
_PREDPONY = ("léčba ", "léčení ", "terapie ", "při ",
              "lecba ", "leceni ", "pri ")


def klic(termin: str | None) -> str:
    """Normalizuje odborny termin na klic slovniku.

    Musi se pouzivat pri STAVBE i pri VYHLEDANI, jinak se klice minou.
    Resi tri veci namerene na realnych datech:
      - koncova interpunkce ("akutni hepatitida." vs "akutni hepatitida")
      - predpona "lecba " ("lecba zaludecnich vredu")
      - zdvojene mezery
    """
    if not termin:
        return ""
    t = " ".join(str(termin).split()).strip().lower()
    t = t.rstrip(".,;:")
    zmena = True
    while zmena:
        zmena = False
        for pre in _PREDPONY:
            if t.startswith(pre):
                t = t[len(pre):].lstrip()
                zmena = True
    return t.strip()


def ocisti_laicky(tvar: str | None) -> str:
    """Hygiena laickeho tvaru: pryc s vetnym ramcem.

    Model casto vraci "Pri obycejnych akne." misto "bezne akne" - je to
    zbytek formulace z vety, ne termin. Do ciselniku patri HOLY tvar,
    protoze se sklada do vlastnich vet pri vypisu.
    """
    if not tvar:
        return ""
    t = " ".join(str(tvar).split()).strip()
    for pre in ("Při ", "při ", "Pri ", "pri "):
        if t.startswith(pre):
            t = t[len(pre):].lstrip()
            # Po odrizu "Pri " zbyva 6. pad ("kozních onemocnenich") -
            # to uz neopravime automaticky, ale aspon nezacina predlozkou.
            break
    return t.rstrip(".").strip()


def nacti(cesta: Path | None = None, *, znovu: bool = False) -> dict[str, str]:
    """Nacte slovnik. Kdyz soubor neexistuje, vrati prazdny - neni to chyba,
    pri prvnim behu jeste neexistuje a extrakce si poradi sama."""
    global _cache
    if _cache is not None and not znovu:
        return _cache

    p = cesta or CESTA
    slovnik: dict[str, str] = {}

    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        # Klice jsou ulozene v malych pismenech, ale radeji to vynutit.
        slovnik = {klic(k): str(v) for k, v in data.items() if v and klic(k)}
    else:
        logger.debug("slovnik %s neexistuje, jede se bez nej", p)

    # Rucni prepisy nakonec - prebijeji vygenerovane.
    if CESTA_RUCNI.exists():
        rucni = json.loads(CESTA_RUCNI.read_text(encoding="utf-8"))
        prepsano = {klic(k): str(v) for k, v in rucni.items()
                    if v and not str(k).startswith("_") and klic(k)}
        slovnik.update(prepsano)
        logger.debug("rucnich prepisu: %d", len(prepsano))

    _cache = slovnik
    return _cache


def rucni_prepisy() -> dict[str, str]:
    """Jen rucni prepisy, at se da poznat, co je overene clovekem."""
    if not CESTA_RUCNI.exists():
        return {}
    data = json.loads(CESTA_RUCNI.read_text(encoding="utf-8"))
    return {klic(k): str(v) for k, v in data.items()
            if v and not str(k).startswith("_") and klic(k)}


def laicky_tvar(odborny: str | None, *, cesta: Path | None = None) -> str | None:
    """Kanonicky laicky tvar terminu, nebo None kdyz ve slovniku neni."""
    if not odborny:
        return None
    return nacti(cesta).get(klic(odborny))


# Dva tvary polozek, ktere v datech existuji:
#   nezadouci_ucinky        {"ucinek": ..., "ucinek_laicky": ...}
#   indikace/kontraindikace {"doslovne": ..., "laicky": ...}
# Slovnik musi umet oba, jinak by indikace zustaly bez dozoru - presne
# to se stalo po sjednoceni tvaru 20.8. a odhalilo se to az na termine
# "neuralgie", ktery mel u kazdeho behu jinou podobu.
TVARY = (("ucinek", "ucinek_laicky"), ("doslovne", "laicky"))


def _tvar(p: dict) -> tuple[str, str] | None:
    """Vrati (pole_odborne, pole_laicke) podle toho, co polozka obsahuje."""
    for odborne, laicke in TVARY:
        if odborne in p:
            return odborne, laicke
    return None


def uplatni(polozky: list, *, cesta: Path | None = None) -> tuple[int, int]:
    """Prepise laicky tvar podle slovniku. Meni polozky NA MISTE.

    Umi oba tvary polozek (viz TVARY).

    Vraci (kolik prepsano ze slovniku, kolik zustalo od modelu).
    Polozky, kde slovnik zasahl, dostanou priznak 'laicky_ze_slovniku',
    aby slo poznat, co je overeny tvar a co jen navrh modelu.
    """
    ze_slovniku = od_modelu = 0
    for p in polozky:
        if not isinstance(p, dict):
            continue
        pole = _tvar(p)
        if pole is None:
            continue
        odborne, laicke = pole
        kanon = laicky_tvar(p.get(odborne), cesta=cesta)
        if kanon:
            p[laicke] = kanon
            p["laicky_ze_slovniku"] = True
            ze_slovniku += 1
        else:
            p.pop("laicky_ze_slovniku", None)
            od_modelu += 1
    return ze_slovniku, od_modelu
