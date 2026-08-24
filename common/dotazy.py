"""Ciselnik pro ROZSIRENI DOTAZU: laicky vyraz -> formulace v textu.

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
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

CESTA = Path("slovnik_dotazu.json")

_cache: dict[str, list[str]] | None = None


def nacti(cesta: Path | None = None, *, znovu: bool = False) -> dict[str, list[str]]:
    global _cache
    if _cache is not None and not znovu:
        return _cache
    p = cesta or CESTA
    if not p.exists():
        _cache = {}
        return _cache
    data = json.loads(p.read_text(encoding="utf-8"))
    _cache = {str(k).strip().lower(): list(v)
              for k, v in data.items()
              if v and not str(k).startswith("_")}
    return _cache


def _bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def rozsir(dotaz: str, *, cesta: Path | None = None, limit: int = 4) -> list[str]:
    """Vrati varianty dotazu VCETNE puvodniho, prvni je vzdy puvodni.

    Hleda klice jako podretezce - uzivatel napise "mám reflux", klic je
    "reflux". Delsi klice maji prednost, aby "pálení žáhy" prebilo
    "žáha", kdyby tam bylo oboje.

    Porovnava se BEZ DIAKRITIKY, protoze lide bezne pisou "kaslu" misto
    "kašlu" - a bge-m3 je na diakritiku citlivy (zmereno: "kasel" vraci
    ABAKTAL misto ACC). Klice jsou proto KMENY ("kasl", ne "kašel"), aby
    prosly i skloňovanim. Hodnoty naopak diakritiku MAJI - prave ony ji
    do hledani vrati.
    """
    if not dotaz:
        return []
    d = _bez_diakritiky(dotaz)
    slovnik = nacti(cesta)
    ven: list[str] = [dotaz]
    for klic in sorted(slovnik, key=len, reverse=True):
        if _bez_diakritiky(klic) in d:
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

CESTA_ATC = Path("atc_mapa.json")

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
