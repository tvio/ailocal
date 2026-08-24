"""Krok 2 pipeline: vytažení jednotlivých sekcí SPC z převedeného dokumentu.

Oproti legacy verzi (regex nad plochým textem) je to výrazně jednodušší –
Docling označí nadpisy jako markdown nadpisy, takže "## 4.8 Nežádoucí účinky"
je jednoznačný záchytný bod a nemusí se hádat podle prázdných řádků.

Volba zdroje textu (viz poznatky.md 14.8.2026):
    sekce obsahuje markdown tabulku  ->  Docling markdown
    neobsahuje                       ->  surový text z PyMuPDF

Důvod: u sekcí bez tabulky markdown nic nepřidává, a u formátu, kde je
označení frekvence na vlastním řádku, Docling slepuje hodnoty a tím
přiřadí účinek ŠPATNÉ frekvenci. Surový text řádkování zachovává.
"""

import re
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Čísla sekcí SPC podle regulatorní struktury (bod 4.1 až 4.9).
SEKCE_SPC = {
    "indikace": "4.1",
    "davkovani": "4.2",
    "kontraindikace": "4.3",
    "nezadouci_ucinky": "4.8",
}

# Sekce, ve kterych se NEURCUJE frekvence. U nich je Docling vzdy lepsi,
# protoze zachova nadpisy skupin pacientu a odrazky. Riziko zamene
# frekvenci, kvuli kteremu se jinde bere surovy text, se jich netyka.
BEZ_FREKVENCI = {"indikace", "kontraindikace"}

# Sekce, která následuje – slouží jako hranice konce té předchozí.
NASLEDUJICI = {
    "4.1": "4.2",
    "4.2": "4.3",
    "4.3": "4.4",
    "4.8": "4.9",
}


@dataclass
class Sekce:
    nazev: str          # 'nezadouci_ucinky'
    cislo: str          # '4.8'
    text: str
    zdroj: str          # 'docling_md' | 'pymupdf_raw'
    ma_tabulku: bool
    nalezena: bool = True


# OCR plete cislice s podobnymi pismeny. TALVOSILEN FORTE mel v SPC
# nadpis "## 4.l Terapeutické indikace" - male L misto jednicky - a sekce
# indikaci se proto NENASLA VUBEC (stav chybi_v_dokumentu), prestoze
# v dokumentu je. Kazda cislice se tedy hleda i ve svych zamenach.
_ZAMENY = {
    "0": "0OoQ",
    "1": "1lI|!",
    "2": "2Z",
    "5": "5S",
    "6": "6G",
    "8": "8B",
    "9": "9g",
}


def _cislo_na_vzor(cislo: str) -> str:
    r"""'4.1' -> '4\.[1lI|!]' - cislice tolerantni k zamenam z OCR."""
    ven = []
    for znak in cislo:
        zameny = _ZAMENY.get(znak)
        ven.append(f"[{re.escape(zameny)}]" if zameny else re.escape(znak))
    return "".join(ven)


def _vzor_nadpisu(cislo: str, *, markdown: bool) -> re.Pattern:
    """Nadpis sekce. V markdownu má mřížky, v surovém textu je na začátku řádku."""
    vzor = _cislo_na_vzor(cislo)
    if markdown:
        return re.compile(rf"^#{{1,6}}\s*{vzor}(?![0-9])\s*\.?\s*", re.MULTILINE)
    # \S musí být v lookaheadu, jinak se ukousne první znak názvu sekce.
    # Oddělovač ale MUSÍ umět i konec řádku – v surovém textu z PyMuPDF bývá
    # číslo sekce na vlastním řádku a název až na dalším ("4.8\nNežádoucí
    # účinky"). Se znakovou třídou [ \t.] se takové sekce vůbec nenašly
    # a spadly na markdownový fallback (78 md / 14 raw místo 21 / 71).
    return re.compile(rf"^\s*{vzor}(?![0-9])[\s.]+(?=\S)", re.MULTILINE)


def vytahni_sekci(text: str, cislo: str, *, markdown: bool) -> str | None:
    """Vrátí text sekce od jejího nadpisu po nadpis následující sekce."""
    zac = _vzor_nadpisu(cislo, markdown=markdown).search(text)
    if not zac:
        return None
    zbytek = text[zac.end():]
    dalsi = NASLEDUJICI.get(cislo)
    if dalsi:
        kon = _vzor_nadpisu(dalsi, markdown=markdown).search(zbytek)
        if kon:
            return zbytek[: kon.start()].strip()
    # Není-li následující nadpis (poslední sekce / jiné číslování), vezmi
    # rozumný kus a nech na extrakci, ať si poradí.
    return zbytek[:40000].strip()


def _ma_tabulku(text: str) -> bool:
    return sum(1 for l in text.splitlines() if l.strip().startswith("|")) >= 3



# --- Oprava rozbitych oznaceni frekvence -----------------------------------
# DITHIADEN mel ve zdroji "V zácné" (rozbite mezerovani z PDF) a model si to
# doplnil na "velmi vzácné" - u VSECH 5 polozek. To je desetinasobne
# podhodnoceni rizika (vzácné = 1/10 000 az 1/1 000, velmi vzácné < 1/10 000).
# sprav_mezerovani() to nechytne, protoze resi osamocene pismeno S DIAKRITIKOU
# obklopene mezerami, kdezto tady je rozdelene obycejne "V" + "zácné".
#
# Nespolehat na to, ze si model poradi - oznaceni frekvence je ridici udaj,
# takze se sceluje deterministicky JESTE PRED tim, nez text uvidi model.

_FREKVENCE_SLOVA = [
    "velmi časté", "velmi vzácné", "méně časté", "není známo",
    "vzácné", "časté",
]


def _vzor_frekvence(slovo: str) -> re.Pattern:
    """Slovo s libovolnymi mezerami mezi znaky: 'V zácné' i 'V z á cné'."""
    znaky = [re.escape(z) for z in slovo if z != " "]
    return re.compile(r"[ 	]*".join(znaky).replace(re.escape(" "), r"[ 	]+"),
                      re.IGNORECASE)


# Delsi vyrazy prvni, jinak by "časté" sezralo kus "velmi časté".
_OPRAVY_FREKVENCE = [
    (_vzor_frekvence(s), s) for s in sorted(_FREKVENCE_SLOVA, key=len, reverse=True)
]


def sceluj_frekvence(text: str) -> str:
    """Slozi zpatky oznaceni frekvence rozbita mezerovanim v PDF.

    Zachovava velikost prvniho pismene, aby se nerozbily nadpisy.
    """
    def nahrad(m: re.Match, kanon: str = "") -> str:
        puvodni = m.group(0)
        return kanon.capitalize() if puvodni[:1].isupper() else kanon

    for vzor, kanon in _OPRAVY_FREKVENCE:
        text = vzor.sub(lambda m, k=kanon: nahrad(m, k), text)
    return text




# --- Rozpad vyctu na radky -------------------------------------------------
# SPC pise vycty indikaci a kontraindikaci jako jednu vetu oddelenou
# STREDNIKY. Model to cte jako souvislou vetu a polovinu polozek slouci
# nebo zahodi. Zmereno na DITHIADENU (sekce 4.1):
#
#     se stredniky      ->  4 polozky
#     stredniky -> radky -> 9 polozek
#
# a zaroven se zlepsila kvalita: "Quinckeho edem" dal se stredniky nesmysl
# "tvarohovy otok obliceje", po rozpadu spravne "nahle otoky kuze a sliznic".
#
# Opravuje se to u ZDROJE, ne v promptu - stejny princip jako u rozbitych
# slov. Prompt uz jednou selhal jako misto pro opravu formatovani.
#
# Carky se NEDELI: uvnitr jedne indikace jsou bezne ("alergicka ryma,
# zvlaste sezonni") a rozpad by je roztrhal na nesmysly.

_STREDNIK = re.compile(r"\s*;\s*")


def rozpad_vyctu(text: str, nazev_sekce: str) -> str:
    """Strednikem oddeleny vycet prevede na radky. Jen u vyctovych sekci."""
    if nazev_sekce not in ("indikace", "kontraindikace"):
        return text
    return _STREDNIK.sub("\n", text)



# --- Propsani nadpisu skupin pacientu do polozek ---------------------------
# SPC deli indikace nadpisem skupiny pacientu a pod nim je odrazkovy seznam:
#
#     ## Dospeli
#     - Lecba duodenalnich vredu
#     - Prevence relapsu duodenalnich vredu
#     ## Pediatricke pouziti
#     Deti od 1 roku a s hmotnosti >= 10 kg
#     - Lecba refluxni ezofagitidy
#
# Zmereno, ze SAMOTNY nadpis nestaci: model u OMEPRAZOLU oznacil jako
# "dospeli" jen tu jednu polozku, kde je "u dospelych" primo ve vete,
# a zbylym deseti pod nadpisem "## Dospeli" dal "neuvedeno".
#
# Proto se skupina propise ke KAZDE polozce jeste pred vstupem do modelu.
# Je to deterministicke - nadpis plati pro vse, co pod nim stoji, az do
# dalsiho nadpisu skupiny.

_NADPIS_SKUPINY = re.compile(
    r"^\s*#{1,6}\s*(.*(?:dosp[ěe]l|dosp[íi]vaj|d[ěe]t|pediatr|kojen|novorozen"
    r"|star[šs][íi]|senior).*?)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE)

# Radek, ktery je sam o sobe upresnenim skupiny ("Deti od 1 roku a s
# hmotnosti >= 10 kg") - stoji pod nadpisem a upresnuje ho.
_UPRESNENI_SKUPINY = re.compile(
    r"^\s*(d[ěe]ti[^.]{0,60}|dosp[ěe]l[íi][^.]{0,40}|dosp[íi]vaj[íi]c[íi][^.]{0,40})\s*$",
    re.IGNORECASE)


def _je_polozka(radek: str) -> bool:
    s = radek.strip()
    return bool(s) and not s.startswith("#")


def oznac_skupiny(text: str, nazev_sekce: str) -> str:
    """Ke kazde polozce dopise skupinu pacientu z nadrazeneho nadpisu.

    Vraci text, kde ma kazda polozka na zacatku "[skupina] ". Model uz
    pak nemusi hadat, ke ktere polozce nadpis patri.
    """
    if nazev_sekce not in BEZ_FREKVENCI:
        return text

    ven: list[str] = []
    skupina: str | None = None
    for radek in text.splitlines():
        m = _NADPIS_SKUPINY.match(radek)
        if m:
            skupina = m.group(1).strip()
            ven.append(radek)
            continue
        if radek.strip().startswith("#"):
            # Jiny nadpis (napr. "Lecba bez porady s lekarem") skupinu RUSI -
            # neni to skupina pacientu a nesmi se propsat.
            skupina = None
            ven.append(radek)
            continue

        if skupina and _je_polozka(radek):
            # Upresneni pod nadpisem skupinu zpresni misto toho, aby se
            # oznacilo jako polozka.
            if _UPRESNENI_SKUPINY.match(radek.strip().lstrip("-* ")):
                skupina = radek.strip().lstrip("-* ")
                ven.append(radek)
                continue
            ven.append(f"[{skupina}] {radek.strip()}")
        else:
            ven.append(radek)
    return "\n".join(ven)

# --- Ořez sekce na jádro ----------------------------------------------------
# Do modelu má jít nezbytné minimum. Sekce SPC obsahují kolem jádra spoustu
# textu, který pro demo nemá cenu: zvláštní populace, popisy jednotlivých
# účinků, regulatorní boilerplate. Ořez je ZÁMĚRNÁ ZTRÁTA INFORMACE –
# proto se nikdy nesmí použít na text, který se ukazuje uživateli, jen
# na vstup do extrakce.

# Podnadpisy v 4.2, za kterými začínají zvláštní případy dávkování.
# Mřížky jsou VOLITELNÉ – 3/4 sekcí jde ze surového PyMuPDF textu,
# kde nadpisy markdownové značky nemají.
_KONEC_DAVKOVANI = re.compile(
    r"^\s*#{0,6}\s*(starší|pediatr|děti|porucha funkce|poruch[ay] ledvin|poruch[ay] jater"
    r"|zvláštní populace|způsob pod|renální|hepatální|snížená funkce)",
    re.IGNORECASE | re.MULTILINE,
)

# Podnadpisy v 4.8, za kterými končí jádro (tabulka / seznam účinků).
_KONEC_NU = re.compile(
    r"^\s*#{0,6}\s*(popis vybran|hlášení podezření|pediatr|další informace"
    r"|dlouhodobé užívání|zvláštní populace|starší)",
    re.IGNORECASE | re.MULTILINE,
)

# Boilerplate, který nesmí do modelu nikdy.
_BOILERPLATE = re.compile(
    r"^\s*#{0,6}\s*hlášení podezření.*", re.IGNORECASE | re.MULTILINE
)


# Vypadá to jako konkrétní dávka? Slouží jako pojistka, že ořez neuřízl
# i samotné dávkování (BISACODYL má hned na začátku 4.2 varování
# "Děti ve věku 10 let nebo mladší ..." – kdyby se řezalo na první shodě,
# nezbylo by z celé sekce nic než nadpis).
# Kratší zbytek než tohle už není "základní dávkování", ale useknutý nadpis.
_MIN_JADRO = 250

_RADEK_FREKVENCE = re.compile(
    r"^(velmi\s+časté|časté|méně\s+časté|velmi\s+vzácné|vzácné|není\s+známo)\s*:",
    re.IGNORECASE,
)

# Nadpis orgánového systému je krátký řádek bez koncové tečky. Delší řádek
# nebo věta zakončená tečkou je próza (definice frekvencí, popis studií)
# a ta se dobírat nesmí.
_MAX_NADPIS = 90


def _zpet_na_nadpis(radky: list[str], i: int) -> int:
    """Posune index nad řádek s frekvencí na nadpis orgánového systému.

    Vrátí původní index, pokud nad ním žádný nadpis není (jsou dokumenty,
    kde seznam frekvencí začíná rovnou, bez orgánových systémů).
    """
    j = i - 1
    while j >= 0 and not radky[j].strip():
        j -= 1
    if j < 0:
        return i
    nadpis = radky[j].strip()
    if len(nadpis) <= _MAX_NADPIS and not nadpis.endswith(".") and not _RADEK_FREKVENCE.match(nadpis):
        return j
    return i


_VYPADA_JAKO_DAVKA = re.compile(
    r"\d[\d,.\s-]*\s*(mg|g|ml|mcg|µg|mikrogram|tablet|kapsl|vstřik|kapk|dávk|%)",
    re.IGNORECASE,
)


def orizni_na_jadro(text: str, nazev_sekce: str) -> str:
    """Zkrátí text sekce na to podstatné pro extrakci.

    davkovani        -> jen základní dávkování, bez zvláštních populací
    nezadouci_ucinky -> jen jádro (tabulka / seznam), bez úvodní prózy,
                        popisů vybraných účinků a hlášení podezření
    ostatní          -> beze změny (jsou krátké)
    """
    if nazev_sekce == "davkovani":
        # Řeže se na PRVNÍM podnadpisu, po kterém ve zbytku pořád zůstane
        # nějaká konkrétní dávka. Klíčové slovo použité ve větě (ne jako
        # nadpis) tak sekci nezlikviduje.
        # Kandidáti = řezy na jednotlivých podnadpisech, odshora.
        kandidati = [text[: m.start()].strip() for m in _KONEC_DAVKOVANI.finditer(text)]

        # Dávkovací tabulka JE dávkování – řez, který ji zahodí, je špatně.
        # V buňkách bývá jen rozsah ("75-200") a jednotka až v hlavičce
        # sloupce, takže test na dávku ji sám o sobě nepozná.
        ma_tabulku = _ma_tabulku(text)

        # 1. volba: nejkratší řez, ve kterém POŘÁD ZŮSTALA konkrétní dávka
        #    (a tabulka, pokud v sekci nějaká je).
        #    Pořadí podmínek je podstatné – dřív tu bylo "dost dlouhé NEBO
        #    obsahuje dávku" a délka kontrolu na dávku přebila: u ALTHYXINU
        #    prošel řez o 795 znacích, ve kterém nebyla ani jedna dávka,
        #    protože celá tabulka s mikrogramy leží až za dalším nadpisem.
        for k in kandidati:
            if ma_tabulku and not _ma_tabulku(k):
                continue
            if _VYPADA_JAKO_DAVKA.search(k):
                return k

        # 2. volba: dávka se nepoznala, ale tabulka zůstala zachovaná.
        if ma_tabulku:
            for k in kandidati:
                if _ma_tabulku(k):
                    return k
            # Tabulka v sekci je, ale žádný řez ji neudrží – typicky proto,
            # že nadpis za ní má rozbité mezerování ("## Z působ pod ání")
            # a jako řezný bod se vůbec nenašel. Radši neřezat než přijít
            # o dávkovací tabulku.
            logger.debug("ořez 4.2 přeskočen, žádný řez neudrží tabulku")
            return text.strip()

        # 3. volba: dávka se nenašla nikde (topické přípravky mají dávkování
        #    slovy – "jednou denně v tenké vrstvě"). Pak stačí, aby po řezu
        #    zbyl souvislý odstavec, ne jen useknutý nadpis.
        for k in kandidati:
            if len(k) >= _MIN_JADRO:
                return k

        return text.strip()

    if nazev_sekce == "nezadouci_ucinky":
        m = _KONEC_NU.search(text)
        jadro = text[: m.start()] if m else text
        # useknout i úvodní prózu před první strukturou (tabulka / nadpis
        # orgánového systému / řádek frekvence) – jsou to definice frekvencí
        # a popis klinických studií, které model nepotřebuje
        radky = jadro.splitlines()
        for i, r in enumerate(radky):
            s = r.strip()
            if s.startswith("|") or s.startswith("#") or _RADEK_FREKVENCE.match(s):
                # Když je první nalezená struktura řádek s frekvencí, leží
                # nad ním nadpis orgánového systému ("Poruchy imunitního
                # systému" / "Není známo: hypersenzitivita"). Bez něj by
                # první účinky přišly o orgánový systém, proto se dobere.
                if _RADEK_FREKVENCE.match(s):
                    i = _zpet_na_nadpis(radky, i)
                jadro = "\n".join(radky[i:])
                break
        return _BOILERPLATE.sub("", jadro).strip()

    return oznac_skupiny(rozpad_vyctu(text.strip(), nazev_sekce), nazev_sekce)


def vytahni_vsechny(adresar: Path) -> dict[str, Sekce]:
    """Vytáhne všechny sledované sekce z jednoho léčiva.

    Očekává v adresáři spc.md (Docling) a spc.pdf (pro surový text).
    """
    from common.konverze import (surovy_text, sprav_mezerovani,
                                 slep_rozdelena_slova, slovnik_dokumentu)

    md_soubor = adresar / "spc.md"
    pdf_soubor = adresar / "spc.pdf"
    if not md_soubor.exists():
        raise FileNotFoundError(f"chybí {md_soubor}")

    # Rozbité mezerování znaků ("zp ů sob") je vada zdrojového PDF, ne
    # extraktoru – postihuje Docling i PyMuPDF stejně. Proto se normalizuje
    # oba zdroje, ne jen surový text.
    md_syrovy = md_soubor.read_text(encoding="utf-8")

    # Slovnik na overovani slepovani se stavi z CELEHO dokumentu, ne jen ze
    # sekce - slovo rozbite mezerou v jedne sekci byva jinde napsane spravne.
    slovnik = slovnik_dokumentu(md_syrovy)

    def uprav(t: str) -> str:
        """Opravy vad ZDROJE (ne extrakce), spolecne pro oba zdroje textu."""
        return sceluj_frekvence(slep_rozdelena_slova(sprav_mezerovani(t), slovnik))

    md = uprav(md_syrovy)
    raw: str | None = None   # načte se líně, jen když je potřeba

    vysledek: dict[str, Sekce] = {}
    for nazev, cislo in SEKCE_SPC.items():
        z_md = vytahni_sekci(md, cislo, markdown=True)

        # Sekce BEZ frekvenci (indikace, kontraindikace) berou VZDY Docling.
        # Puvodni pravidlo "bez tabulky -> plain text" vzniklo kvuli zamene
        # frekvenci v sekci 4.8 - jenze tyhle sekce zadne frekvence nemaji,
        # takze se na ne ten duvod nikdy nevztahoval. Aplikoval jsem ho
        # plosne zbytecne a stalo to strukturu:
        #
        #     Docling:     15 nadpisu, 122 odrazek
        #     plain text:   0 nadpisu,  82 odrazek
        #
        # Nulove nadpisy znamenaji, ze se ztratilo rozdeleni na skupiny
        # pacientu ("## Dospeli", "## Pediatricke pouziti") a model pak
        # musel hadat, ke ktere polozce skupina patri. U OMEPRAZOLU proto
        # oznacil jako "dospeli" jen prvni indikaci z jedenacti.
        if nazev in BEZ_FREKVENCI and z_md:
            vysledek[nazev] = Sekce(nazev, cislo, z_md, "docling_md",
                                    _ma_tabulku(z_md))
            continue

        if z_md and _ma_tabulku(z_md):
            vysledek[nazev] = Sekce(nazev, cislo, z_md, "docling_md", True)
            continue

        # Bez tabulky bereme surový text – markdown by nic nepřidal a hrozí
        # záměna frekvencí. Když se v surovém textu sekce nenajde, spadneme
        # zpátky na markdown (lepší něco než nic).
        if raw is None:
            raw = uprav(surovy_text(pdf_soubor)) if pdf_soubor.exists() else ""
        z_raw = vytahni_sekci(raw, cislo, markdown=False) if raw else None

        if z_raw:
            vysledek[nazev] = Sekce(nazev, cislo, z_raw, "pymupdf_raw", False)
        elif z_md:
            vysledek[nazev] = Sekce(nazev, cislo, z_md, "docling_md", False)
        else:
            vysledek[nazev] = Sekce(nazev, cislo, "", "zadny", False, nalezena=False)

    return vysledek
