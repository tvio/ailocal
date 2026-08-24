"""Konverze SPC PDF do Markdownu přes Docling + ořez EU dokumentů.

Proč Docling a ne prostý text z PyMuPDF: v legacy fázi se ukázalo, že plochý
text nerozliší nadpis od běžného textu a MedDRA tabulku nežádoucích účinků
zploští do proudu řádků. Pak se muselo hádat regexem podle prázdných řádků
a tabulka se řezala napůl. Docling vrací nadpisy jako markdown nadpisy
a tabulky jako markdown tabulky, takže se dá řezat podle skutečné struktury.
"""

import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field

# MUSÍ být nastaveno DŘÍV, než se importuje torch (Docling si ho tahá sám).
# Bez toho konverze na Windows spadne s:
#     ConversionError: InvalidCxxCompiler: Compiler: cl is not found
# Torch se pokouší JIT kompilovat přes torch.compile, hledá MSVC (cl.exe),
# nenajde ho a shodí celou konverzi – není to jen varování.
# Alternativa by byla doinstalovat Visual C++ Build Tools, ale pro naše
# použití (jen inference layout modelu) není torch.compile potřeba.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

logger = logging.getLogger(__name__)

# Nadpis, kterým u EU registrací začíná druhá část dokumentu.
# EU dokument je slepenec: Příloha I = SPC (chceme), Příloha II a dál =
# podmínky registrace, označení na obalu, příbalová informace (nechceme).
EU_KONEC = re.compile(r"^#{1,6}\s*P[ŘR]ÍLOHA\s+II\b", re.IGNORECASE | re.MULTILINE)

# Totéž, ale pro hledání v surovém textu PDF (bez markdown mřížek).
# Musí být "II" a ne "III" – proto negativní lookahead na další I.
EU_KONEC_PDF = re.compile(r"P[ŘR]ÍLOHA\s+II(?!I)\b", re.IGNORECASE)


def najdi_stranu_prilohy_II(cesta_pdf: Path) -> int | None:
    """Najde číslo stránky (1-based), kde u EU registrace začíná Příloha II.

    Vrací None u CZ registrací, kde je SPC samostatný dokument bez příloh.
    """
    import pymupdf

    doc = pymupdf.open(str(cesta_pdf))
    try:
        for i, page in enumerate(doc, start=1):
            if EU_KONEC_PDF.search(page.get_text("text")):
                return i
    finally:
        doc.close()
    return None


def orizni_pdf_pred_konverzi(cesta_pdf: Path, *, cil: Path | None = None) -> tuple[Path, int | None, int]:
    """Ořízne PDF na stránky před Přílohou II a uloží jako nový soubor.

    Dělá se to PŘED konverzí Doclingem, ne po ní – Docling je nejpomalejší
    krok pipeline (0,3–3 s na stránku) a u EU dokumentů je většina stránek
    k zahození. U OLANZAPINu je Příloha II na straně 20 z 96, takže se
    ušetří přes 80 % práce.

    Vrací (cesta_k_pouziti, strana_prilohy_II, pocet_stran_ke_konverzi).
    Čísla stránek zůstávají shodná s originálem, takže odkazy do PDF platí.
    """
    import pymupdf

    strana = najdi_stranu_prilohy_II(cesta_pdf)
    doc = pymupdf.open(str(cesta_pdf))
    celkem = doc.page_count

    if strana is None or strana <= 1:
        doc.close()
        return cesta_pdf, None, celkem

    cil = cil or cesta_pdf.with_name("spc_orez.pdf")
    orez = pymupdf.open()
    orez.insert_pdf(doc, from_page=0, to_page=strana - 2)   # 0-based, bez strany s Přílohou II
    orez.save(str(cil))
    pocet = orez.page_count
    orez.close()
    doc.close()

    logger.info(
        "  ořez EU: Příloha II na str. %d – konvertuje se %d z %d stran (−%d %%)",
        strana, pocet, celkem, round((1 - pocet / celkem) * 100),
    )
    return cil, strana, pocet


@dataclass
class VysledekKonverze:
    markdown: str
    strany_celkem: int          # kolik měl původní PDF
    strany_konvertovane: int    # kolik jich šlo do Doclingu (po ořezu)
    orezano: bool = False
    strana_prilohy_II: int | None = None
    nadpisy: list[str] = field(default_factory=list)
    strany_nadpisu: dict[str, int] = field(default_factory=dict)
    pocet_tabulek: int = 0


def orizni_eu_dokument(md: str) -> tuple[str, int | None]:
    """U EU registrací ořízne vše od nadpisu 'PŘÍLOHA II' dál (včetně něj).

    Vrací (oříznutý_markdown, pozice_ořezu) – pozice je None, když se
    nadpis nenašel (typicky u CZ registrací, kde je SPC samostatný soubor).
    """
    m = EU_KONEC.search(md)
    if not m:
        return md, None
    return md[: m.start()].rstrip(), m.start()


def konvertuj_pdf(cesta_pdf: Path, *, orezat_eu: bool = True) -> VysledekKonverze:
    """PDF -> Markdown přes Docling.

    U EU registrací se PDF nejdřív ořízne na stránky před Přílohou II
    (PyMuPDF, řádově milisekundy) a teprve ořezané jde do Doclingu.
    Ořez PŘED konverzí, ne po ní – Docling je nejdražší krok pipeline.
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

    ke_konverzi = cesta_pdf
    strana_prilohy = None
    stran_konvertovanych = 0
    import pymupdf

    with pymupdf.open(str(cesta_pdf)) as d:
        stran_celkem = d.page_count

    if orezat_eu:
        ke_konverzi, strana_prilohy, stran_konvertovanych = orizni_pdf_pred_konverzi(cesta_pdf)
    else:
        stran_konvertovanych = stran_celkem

    # Textovy backend se NEsmi nechat na vychozim (docling_parse_v4) - ten
    # rozbiji slova mezerami ("P acienti", "V zacne"). Zmereno na korpusu:
    #
    #     PyMuPDF        64 rozbitych mist
    #     Docling v4   1232 rozbitych mist   <- 19x vic nad TEMIZ PDF
    #
    # Neni to tedy vada zdrojovych PDF, ale toho backendu. pypdfium2 to
    # snizi radove (ALTHYXIN 363 -> 4, CONTROLOC 237 -> 10) a TABULKY
    # zustavaji shodne (17/17, 39/39 radku), protoze ty dela layout model,
    # ne textovy backend. Navic je o neco rychlejsi.
    #
    # Oprava u ZDROJE je lepsi nez slepovat slova zpetne - slepovani nikdy
    # nemuze byt uplne a nese riziko, ze slepi neco spatne ("ze na" -> "zena").
    prevodnik = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(backend=PyPdfiumDocumentBackend)}
    )
    vysledek = prevodnik.convert(str(ke_konverzi))
    dokument = vysledek.document

    md = dokument.export_to_markdown()

    # Čísla stránek k nadpisům – potřeba pro odkaz "spc.pdf#page=7" ve výsledcích.
    strany_nadpisu: dict[str, int] = {}
    nadpisy: list[str] = []
    for text in getattr(dokument, "texts", []) or []:
        label = str(getattr(text, "label", ""))
        if "section_header" not in label and "title" not in label:
            continue
        popis = (getattr(text, "text", "") or "").strip()
        if not popis:
            continue
        nadpisy.append(popis)
        prov = getattr(text, "prov", None) or []
        if prov:
            strana = getattr(prov[0], "page_no", None)
            if strana is not None:
                strany_nadpisu.setdefault(popis, strana)

    # Pojistka: kdyby ořez podle stránek nezabral (jiné formátování dokumentu),
    # zkusí se ještě ořez na úrovni markdownu.
    md_orez, pozice = orizni_eu_dokument(md)
    if pozice is not None:
        md = md_orez
        nadpisy = [n for n in nadpisy if n in md]
        logger.info("  ořez EU: dodatečně na úrovni markdownu (stránkový nezabral)")

    return VysledekKonverze(
        markdown=md,
        strany_celkem=stran_celkem,
        strany_konvertovane=stran_konvertovanych,
        orezano=strana_prilohy is not None or pozice is not None,
        strana_prilohy_II=strana_prilohy,
        nadpisy=nadpisy,
        strany_nadpisu=strany_nadpisu,
        pocet_tabulek=len(getattr(dokument, "tables", []) or []),
    )


def spocitej_md_tabulky(md: str) -> int:
    """Kolik markdown tabulek je v textu (řádky s | oddělovači)."""
    return len(re.findall(r"^\|.+\|\s*$\n^\|[\s:|-]+\|\s*$", md, re.MULTILINE))


# Osamocené písmeno s diakritikou mezi dvěma písmeny = rozbité mezerování
# znaků v PDF ("zp ů sob" místo "způsob"). Vyskytuje se u některých PDF
# kvůli špatným šířkám mezer ve fontu – postihuje to i Docling, není to
# vada extraktoru. Naměřeno u 1 z 23 dokumentů (ALTHYXIN, 7 % slov).
#
# Bezpečnost pravidla: písmena s diakritikou (ě š č ř ž ý á í é ú ů ď ť ň)
# nejsou v češtině samostatná slova, na rozdíl od a/i/k/o/s/u/v/z. Proto
# se opravují jen ona a spojka nemůže omylem slepit dvě legitimní slova.
ROZBITE_MEZEROVANI = re.compile(
    r"(?<=[^\W\d_])\s([ěščřžýáíéúůďťňĚŠČŘŽÝÁÍÉÚŮĎŤŇ])\s(?=[^\W\d_])"
)


def sprav_mezerovani(text: str) -> str:
    """Opraví rozbité mezerování znaků typu 'zp ů sob' -> 'způsob'.

    Řeší jen jednoznačný případ osamoceného písmene s diakritikou.
    Zbytek (např. 'mikrogr amů') zůstává – na to už si musí poradit
    model při extrakci, regexem by to nešlo spolehlivě rozlišit
    od legitimního dělení.
    """
    predchozi = None
    # Opakovaně, protože sousedící výskyty se překrývají ("lé č b y")
    while predchozi != text:
        predchozi = text
        text = ROZBITE_MEZEROVANI.sub(r"\1", text)
    return text


def surovy_text(cesta_pdf: Path) -> str:
    """Text z PDF přes PyMuPDF, se zachovaným řádkováním.

    Používá se pro sekce, kde Docling nevyrobil tabulku – tam markdown
    nic nepřidává a naopak hrozí, že Docling slepí řádky a tím posune
    přiřazení frekvencí k účinkům (ověřeno na IFIRMASTĚ, viz poznatky.md).
    """
    import pymupdf

    with pymupdf.open(str(cesta_pdf)) as doc:
        return "\n".join(p.get_text("text") for p in doc)


# --- Slepovani slov rozbitych mezerou --------------------------------------
# PDF ze SUKL casto rozdeli slovo mezerou: "P acienti", "srd ecni", "T ridy",
# "Psychi atricke". Zmereno: 86 takovych mist v 18 z 92 sekci korpusu.
# Neni to kosmetika - "V zacne" vedlo k tomu, ze model zapsal "velmi vzacne"
# misto "vzacne", tedy DESETINASOBNE podhodnoceni rizika (viz poznatky.md).
#
# Slepovat naslepo NELZE: "C pri" by dalo nesmysl "Cpri", "viz bod" by se
# slepilo na "vizbod". Proto se slepi jen tehdy, kdyz slepenec EXISTUJE
# jinde v temze dokumentu jako radne slovo - dokument si tak overuje sam
# sebe. Zmereno, ze slovnik z vlastniho spc.md pokryje 73 ze 76 mist,
# tedy prakticky stejne jako slovnik z celeho korpusu.

_SLOVO = re.compile(r"[^\W\d_]+", re.UNICODE)

# Dvojice "kratky kus" + mezera + "zbytek slova". Prvni cast max 6 znaku -
# delsi uz nejsou zlomy, ale dve ruzna slova.
_DVOJICE = re.compile(r"(?<![^\W\d_])([^\W\d_]{1,6}) ([^\W\d_]{2,})", re.UNICODE)

# Ceska jednoslabicna slova a zkratky, ktere se NIKDY neslepuji.
_NESLEPOVAT = {
    "a", "i", "o", "u", "k", "s", "v", "z", "do", "na", "po", "za", "ve", "se",
    "ke", "je", "od", "ze", "to", "co", "by", "ne", "tj", "mg", "ml", "kg",
    "aj", "viz", "ma", "byt", "pro", "let", "az", "aby", "vsak", "tzv", "cca",
}


# Kolikrat musi kratky retezec stat v dokumentu samostatne, aby se bral
# jako skutecne slovo a NEslepoval se s nasledujicim. Zmereno: "ze" stoji
# samostatne mnohokrat (spojka), kdezto "C" z "25 °C" jen parkrat - prah 3
# oboji rozdeli. Bez toho se "ze na jejich vzniku" slepilo na "zena".
_PRAH_SAMOSTATNEHO_SLOVA = 3


def slovnik_dokumentu(text: str, *, min_delka: int = 4) -> tuple[set[str], set[str]]:
    """Vrati (slova pro overeni slepence, slova ktera se neslepuji).

    Prvni mnozina: dost dlouha slova z dokumentu - proti nim se overuje,
    jestli slepenec vubec existuje.
    Druha mnozina: retezce, ktere v dokumentu stoji samostatne dost casto
    na to, aby to byla skutecna slova (typicky spojky a predlozky).
    """
    from collections import Counter

    vyskyty = Counter(w.lower() for w in _SLOVO.findall(text))
    slepence = {w for w, n in vyskyty.items() if len(w) >= min_delka}
    # Jen retezce delky 2+. Jednopismenna slova ma cestina presne osm
    # (a i o u k s v z) a ta jsou v _NESLEPOVAT; ostatni jednotliva pismena
    # jsou artefakty tabulek ("C" z "25 °C", "P" ze zacatku rozbiteho slova)
    # a ta se slepovat MAJI - jinak prijdeme o "C evni" -> "Cevni".
    samostatna = {w for w, n in vyskyty.items()
                  if n >= _PRAH_SAMOSTATNEHO_SLOVA and 2 <= len(w) < min_delka}
    return slepence, samostatna


def slep_rozdelena_slova(text: str, slovnik: tuple[set[str], set[str]]) -> str:
    """Slepi slova rozbita mezerou, ale JEN kdyz slepenec je ve slovniku.

    Slovnik ma pochazet z tehoz dokumentu (viz slovnik_dokumentu) - slovo
    rozbite na jednom miste byva jinde v dokumentu napsane spravne.
    """
    slepence, samostatna = slovnik

    def nahrad(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        prvni = a.lower()
        # Prvni cast je skutecne slovo -> neni to zlom, ale dve slova.
        if prvni in _NESLEPOVAT or prvni in slepence or prvni in samostatna:
            return m.group(0)
        if (a + b).lower() in slepence:
            return a + b
        return m.group(0)

    return _DVOJICE.sub(nahrad, text)
