"""Normalizace nazvu organovych systemu (MedDRA SOC) na rizeny slovnik.

Proc to je potreba: `organovy_system` ma byt FILTR - uzivatel nevi, co je
tachykardie, ale umi rict "srdce". Filtr ale funguje jen tehdy, kdyz ma
kazda kategorie jeden tvar. V korpusu 23 leciv bylo 31 ruznych hodnot,
pritom skutecnych kategorii je ~20. Rozdil delaly:

    rozbite mezerovani z PDF   "Psychiatricke p oruchy", "C evni poruchy"
    znacky poznamek pod carou  "Poruchy nervoveho systemu*"
    zavorky navic              "Poruchy imunitniho systemu (viz bod 4.3)"
    preklep modelu             "v misto aplikace" (8x),
                               "mediální" misto "mediastinalni"

Vetsinu z toho spravi normalizace (bez mezer a diakritiky), zbytek
priblizna shoda proti kanonickemu seznamu - stejna technika jako
u oprav preklepu v nazvech klicu (viz extrakce._oprav_klice).

DULEZITE: tohle NEPOTREBUJE model. Zdrojova data uz jsou vytazena,
tohle je jen ocisteni - da se pustit opakovane a je zadarmo.
"""

import re
import unicodedata
from difflib import get_close_matches

# Kanonicke nazvy MedDRA System Organ Class v cestine. Prevzato z tvaru,
# ktere se v korpusu vyskytuji nejcasteji (ty jsou spravne), doplneno
# o dalsi standardni tridy, aby to snesl i rozsireny korpus.
SOC_KANONICKE = [
    "Infekce a infestace",
    "Novotvary benigní, maligní a blíže neurčené",
    "Poruchy krve a lymfatického systému",
    "Poruchy imunitního systému",
    "Endokrinní poruchy",
    "Poruchy metabolismu a výživy",
    "Psychiatrické poruchy",
    "Poruchy nervového systému",
    "Poruchy oka",
    "Poruchy ucha a labyrintu",
    "Srdeční poruchy",
    "Cévní poruchy",
    "Respirační, hrudní a mediastinální poruchy",
    "Gastrointestinální poruchy",
    "Poruchy jater a žlučových cest",
    "Poruchy kůže a podkožní tkáně",
    "Poruchy svalové a kosterní soustavy a pojivové tkáně",
    "Poruchy ledvin a močových cest",
    "Stavy spojené s těhotenstvím, šestinedělím a perinatálním obdobím",
    "Poruchy reprodukčního systému a prsu",
    "Vrozené, familiární a genetické vady",
    "Celkové poruchy a reakce v místě aplikace",
    "Vyšetření",
    "Poranění, otravy a procedurální komplikace",
    "Chirurgické a léčebné postupy",
    "Sociální okolnosti",
]

# Prah pribuznosti pro pripojeni na kanonicky tvar. Nizsi nez u klicu (0,7),
# protoze nazvy SOC jsou dlouhe - i "mediální" misto "mediastinální" je
# pri delce 40+ znaku porad velmi podobny retezec.
PRAH = 0.85

# Co se pred porovnanim odstrani: znacky poznamek a zavorkove odkazy.
_SMETI = re.compile(r"\s*\((?:viz|see)[^)]*\)|[*†‡]+", re.IGNORECASE)


def _klic(s: str) -> str:
    """Porovnavaci tvar: bez diakritiky, bez mezer a interpunkce, mala pismena."""
    bez = "".join(z for z in unicodedata.normalize("NFKD", str(s))
                  if not unicodedata.combining(z))
    return re.sub(r"[^a-z0-9]", "", bez.lower())


_INDEX = {_klic(s): s for s in SOC_KANONICKE}


def normalizuj_soc(hodnota: str | None) -> tuple[str | None, str]:
    """Vrati (kanonicky nazev, jak se to podarilo).

    Druhy vysledek je jeden z:
        'presna'   - po ocisteni presna shoda s kanonickym nazvem
        'pribuzna' - pripojeno pres podobnost (preklep, rozbite mezerovani)
        'nezname'  - nesedi na nic, vraci se puvodni hodnota
        'prazdna'  - nebylo co normalizovat
    """
    if not hodnota or not str(hodnota).strip():
        return None, "prazdna"

    ocistene = _SMETI.sub("", str(hodnota)).strip(" .:;,")
    k = _klic(ocistene)
    if not k:
        return None, "prazdna"

    if k in _INDEX:
        return _INDEX[k], "presna"

    blizke = get_close_matches(k, _INDEX.keys(), n=1, cutoff=PRAH)
    if blizke:
        return _INDEX[blizke[0]], "pribuzna"

    return ocistene, "nezname"
