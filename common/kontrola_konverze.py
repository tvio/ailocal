"""Kontroly kvality převodu PDF -> Markdown. Referencí je PDF, NE Docling.

Vzniklo z benchmarku `benchmarky/pdfextrakce` (poznatky.md 24.9.2026),
kde se ukázalo, že Docling sám chybuje třemi způsoby, které se v datech
tiše projeví:

  1. ZTRÁTA / PŘESKLÁDÁNÍ TEXTU sekce 4.8 (CASARO: 35 % slov sekce leželo
     za nadpisem 4.9). -> pokryti_48()
  2. POSUN SLOUPCE v tabulce, kde sloupce jsou frekvence (AUBAGIO:
     „Chřipka" v „Velmi časté", v PDF leží pod „Časté"). -> sloupce_frekvenci()
  3. FALEŠNÉ NADPISY z obyčejných vět (ACECOR „Přípravek je indikován:").
     -> falesne_nadpisy()

Všechny kontroly čtou jen Markdown a PDF (PyMuPDF), Docling znovu
nespouští. Vrací čísla; o tom, co je „podezřelé", rozhoduje volající.
"""

import re
from collections import Counter
from pathlib import Path

# Jen SKUTEČNÉ HTML značky (<u>, <br>, <sup>). Obecné <[^>]+> bralo za
# značku i "<" ve frekvencích ("až < 1/10") a mazalo text k dalšímu ">".
_ZNACKA = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]{0,9}(\s[^<>]{0,80})?/?>")

KANON = ["velmi časté", "časté", "méně časté", "vzácné", "velmi vzácné", "není známo"]


def cisty(radek: str) -> str:
    """Řádek bez markdownu/HTML – pro hledání nadpisů v jakémkoli formátu."""
    s = re.sub(r"[#*_|]", " ", _ZNACKA.sub(" ", radek))
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def _sekce_md(md: str, cislo: str) -> str:
    """Sekce z Markdownu – STEJNÉ hledání nadpisů jako extrakce (common/sekce.py).

    Kontrola měla dřív vlastní, slabší kopii pravidel a padala na tvarech,
    které produkce zvládá: „4. 8.", „## 4.8.Nežádoucí" (ERMM-1: pokrytí 0 %,
    přestože sekce byla celá), zalomený odkaz „4.8)." (PARALEN 93 % -> 14 %).
    Jedno místo pro pravidla = kontrola i extrakce najdou sekci stejně.
    """
    from common.sekce import vytahni_sekci
    return vytahni_sekci(md, cislo, markdown=True) or ""


def _sekce_pdf(text: str, cislo: str) -> str:
    """Sekce ze surového textu PDF – stejné pravidlo jako extrakce."""
    from common.sekce import vytahni_sekci
    return vytahni_sekci(text, cislo, markdown=False) or ""


def slova(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]{3,}", _ZNACKA.sub(" ", text).lower())


# --- 1) pokrytí textu --------------------------------------------------------
def pokryti_48(md: str, surovy_text: str) -> float | None:
    """Podíl slov sekce 4.8 ze SUROVÉHO textu PDF, která jsou i v Markdownu.

    None = sekce se v PDF nenašla (NESMÍ se brát jako 100 % – tak se
    v benchmarku schoval CHAMPIX). Chybějící slovo, které je jinde
    v dokumentu, znamená přeskládání; které není nikde, ztrátu.
    """
    pdf = Counter(slova(_sekce_pdf(surovy_text, "4.8")))
    if not pdf:
        return None
    v = Counter(slova(_sekce_md(md, "4.8")))
    return sum(min(n, v[w]) for w, n in pdf.items()) / sum(pdf.values())


# --- 2) sloupce frekvencí ---------------------------------------------------
def _frek(s: str) -> str | None:
    s = re.sub(r"\s+", " ", cisty(s).lower()).strip(" :")
    for k in sorted(KANON, key=len, reverse=True):
        if s.startswith(k):
            return k
    return None


def _bunky_formatu2(md: str) -> list[tuple[str, str]]:
    """(text buňky, frekvence podle záhlaví sloupce) z tabulek sekce 4.8,
    kde záhlaví tvoří aspoň dvě frekvence (formát 2)."""
    ven, hlav = [], None
    for radek in _sekce_md(md, "4.8").splitlines():
        r = radek.strip()
        if not (r.startswith("|") and r.endswith("|")):
            hlav = None
            continue
        bunky = r[1:-1].split("|")
        if all(re.fullmatch(r"\s*:?-{2,}:?\s*", b) or not b.strip() for b in bunky):
            continue
        f = [_frek(b) for b in bunky]
        if sum(bool(x) for x in f) >= 2:
            hlav = f
            continue
        # Řádek přes celou šířku (název orgánové třídy): Docling ho opakuje
        # v KAŽDÉM sloupci. Není to účinek – DEPREX jinak hlásil 36/62
        # „špatných sloupců", všechny tohoto druhu.
        nepr = {cisty(b) for b in bunky if cisty(b)}
        if len(nepr) == 1:
            continue
        if hlav:
            for i, b in enumerate(bunky):
                t = cisty(b)
                if len(t) >= 4 and i < len(hlav) and hlav[i] and not _frek(t):
                    ven.append((t, hlav[i]))
    return ven


def _sloupce_tabulek(stranka, predchozi):
    """[(y0, y1, [(x0, x1, frekvence)])] pro tabulky na stránce, kde
    záhlaví tvoří frekvence. Hranice sloupců jsou SKUTEČNÉ buňky tabulky
    (PyMuPDF find_tables).

    První verze odhadovala hranici jako polovinu mezi středy záhlaví; při
    nestejně širokých sloupcích pak text u levého okraje sloupce spadl do
    sousedního (SOLIFENACIN, RISPERDAL CONSTA – falešné „špatné sloupce").
    Tabulka pokračující z minulé stránky bez záhlaví převezme sloupce
    z `predchozi`.
    """
    ven = []
    for t in stranka.find_tables().tables:
        radky = t.extract()
        sloupce = None
        for ri, r in enumerate(radky):
            f = [_frek(x or "") for x in r]
            if sum(bool(x) for x in f) >= 2:
                bunky = t.rows[ri].cells
                sloupce = [(b[0], b[2], fx) for b, fx in zip(bunky, f) if b and fx]
                break
        if sloupce is None and predchozi:
            sloupce = predchozi
        if sloupce:
            ven.append((t.bbox[1], t.bbox[3], sloupce))
            predchozi = sloupce
    return ven, predchozi


def sloupce_frekvenci(md: str, pdf: Path, strana_od: int) -> dict:
    """Ověří, že účinek v tabulce formátu 2 je ve sloupci té frekvence,
    pod jejímž záhlavím leží v PDF.

    Buňka se v PDF hledá podle PRVNÍCH DVOU slov za sebou (jedno slovo
    typu „bolest" bývá na stránce víckrát). Sloupec = buňka tabulky v PDF,
    do které slovo padne. Nenalezené / nejednoznačné se nepočítají.
    """
    import pymupdf

    bunky = _bunky_formatu2(md)
    vysl = {"bunek": len(bunky), "overeno": 0, "spatne": 0, "priklady": []}
    if not bunky:
        return vysl
    with pymupdf.open(str(pdf)) as d:
        stranky, predchozi = [], None
        for s in range(max(strana_od, 1), min(strana_od + 5, d.page_count + 1)):
            p = d[s - 1]
            tab, predchozi = _sloupce_tabulek(p, predchozi)
            stranky.append((p.get_text("words"), tab))
    # Jednoslovná buňka („Chřipka", „úzkost") se ověřuje jen tehdy, když
    # je to slovo na prověřovaných stranách JEDINKRÁT – jinak nejde říct,
    # který výskyt je ta buňka.
    vyskyty = Counter(x for w, _ in stranky for s in w for x in slova(s[4]))
    for text, f_md in bunky:
        kl = slova(text)[:2]
        if not kl or (len(kl) == 1 and vyskyty[kl[0]] != 1):
            continue
        nalez = []
        for w, tab in stranky:
            for i in range(len(w)):
                kus = w[i][4] + (" " + w[i + 1][4] if len(kl) == 2 and i + 1 < len(w) else "")
                if slova(kus)[:len(kl)] != kl:
                    continue
                x, y = w[i][0] + 1, (w[i][1] + w[i][3]) / 2
                for y0, y1, sloupce in tab:
                    if not (y0 <= y <= y1):
                        continue
                    nalez += [f for x0, x1, f in sloupce if x0 <= x < x1]
        if len(set(nalez)) != 1:
            continue                        # nenalezeno nebo nejednoznačné
        vysl["overeno"] += 1
        if nalez[0] != f_md:
            vysl["spatne"] += 1
            if len(vysl["priklady"]) < 5:
                vysl["priklady"].append(f"{text[:50]}: md={f_md}, pdf={nalez[0]}")
    return vysl


# --- 2b) frekvence proti STRUKTURNÍM ZNAČKÁM PDF --------------------------------
# 94 % SPC jsou tagovaná PDF z Wordu: Table/TR/TH/TD nesou tabulku, jak ji
# autor postavil. Přesnější reference než odhad sloupců z geometrie.
# Tři pasti (poznatky.md 25.9.): sloučenou buňku přes víc řádků Word do
# značek NEZAPÍŠE -> sloupec z POLOHY buňky (bbox), ne z pořadí; ořez PDF
# značky zahodí -> číst ORIGINÁL; buňky se dělí různě -> měřit po SLOVECH.
_BUNKA_ZNACKY = {"TD", "TH"}


def _text_znacky(e) -> str:
    return re.sub(r"\s+", " ", "".join(c.get("c", "") for c in e.iter("char"))).strip()


def _prvky_znacek(pdf: Path):
    """Strukturní prvky pod Document v pořadí napříč stránkami."""
    import pymupdf
    import xml.etree.ElementTree as ET

    with pymupdf.open(str(pdf)) as d:
        for p in d:
            try:
                koren = ET.fromstring(p.get_text("xml", flags=pymupdf.TEXT_COLLECT_STRUCTURE))
            except ET.ParseError:
                continue
            for s in koren.iter("struct"):
                if s.get("raw") == "Document":
                    yield from (c for c in s if c.tag == "struct")
                    break
            else:
                yield from (c for c in koren if c.tag == "struct")


def _tabulka_znacek(e) -> list[list[str]]:
    def bbox(x):
        try:
            v = [float(t) for t in x.get("bbox", "").split()]
            return v if len(v) == 4 else None
        except ValueError:
            return None

    radky = []
    for tr in e.iter("struct"):
        if tr.get("raw") == "TR":
            b = [(_text_znacky(td), bbox(td)) for td in tr
                 if td.tag == "struct" and td.get("raw") in _BUNKA_ZNACKY]
            if any(t for t, _ in b):
                radky.append(b)
    if not radky:
        return []
    sloupce = [bb for _, bb in max(radky, key=len)]
    if not all(sloupce):
        return [[t for t, _ in r] for r in radky]
    ven = []
    for r in radky:
        rad = [""] * len(sloupce)
        for t, bb in r:
            if not bb:
                continue
            st = (bb[0] + bb[2]) / 2
            i = min(range(len(sloupce)), key=lambda k: 0 if sloupce[k][0] <= st <= sloupce[k][2]
                    else min(abs(st - sloupce[k][0]), abs(st - sloupce[k][2])))
            rad[i] = (rad[i] + " " + t).strip()
        ven.append(rad)
    return ven


def tabulky_48_ze_znacek(pdf_original: Path) -> list[list[list[str]]] | None:
    """Tabulky sekce 4.8 ze značek. None = PDF značky nemá."""
    if b"/StructTreeRoot" not in pdf_original.read_bytes():
        return None
    ven, v48 = [], False
    for e in _prvky_znacek(pdf_original):
        if e.get("raw") == "Table":
            if v48 and (tab := _tabulka_znacek(e)):
                ven.append(tab)
            continue
        text = _text_znacky(e)
        if re.match(r"^4\s*\.\s*8\s*\.?(\s|$)", text):
            v48 = True
        elif v48 and re.match(r"^(4\s*\.\s*9|5\s*\.)\s*\.?(\s|$)", text):
            break
    return ven


def _slova_pod_frekvencemi(radky) -> dict[str, Counter]:
    """Frekvence -> slova ve sloupci té frekvence. `radky` = seznamy buněk
    v pořadí; řádek se ≥2 frekvencemi je záhlaví."""
    ven: dict[str, Counter] = {}
    hlav = None
    for r in radky:
        if r is None:
            hlav = None
            continue
        f = [_frek(x) for x in r]
        if sum(bool(x) for x in f) >= 2:
            hlav = f
            continue
        if not hlav or len({cisty(x) for x in r if cisty(x)}) <= 1:
            continue                           # bez záhlaví / přes celou šířku
        for i, x in enumerate(r):
            fi = hlav[i] if i < len(hlav) else None
            if fi and not _frek(x):
                ven.setdefault(fi, Counter()).update(slova(x))
    return ven


def _radky_md(md: str):
    for radek in _sekce_md(md, "4.8").splitlines():
        r = radek.strip()
        if not (r.startswith("|") and r.endswith("|")):
            yield None
            continue
        bunky = r[1:-1].split("|")
        if all(re.fullmatch(r"\s*:?-{2,}:?\s*", b) or not b.strip() for b in bunky):
            continue
        yield bunky


def frekvence_proti_znackam(md: str, pdf_original: Path) -> dict | None:
    """Slova tabulek 4.8: správná / JINÁ frekvence / chybí, proti značkám.
    None = značky nejsou nebo v 4.8 nemají tabulku (-> geometrická kontrola)."""
    tab = tabulky_48_ze_znacek(pdf_original)
    if not tab:
        return None
    radky = []
    for t in tab:
        radky += t + [None]
    ref = _slova_pod_frekvencemi(radky)
    if not ref:
        return None
    var = _slova_pod_frekvencemi(_radky_md(md))
    vse_ref: Counter = Counter()
    vse_var: Counter = Counter()
    for c in ref.values():
        vse_ref.update(c)
    for c in var.values():
        vse_var.update(c)
    celkem = spravne = jinde = 0
    priklady: list[str] = []
    for w, n in vse_ref.items():
        ok = sum(min(ref[f][w], var.get(f, Counter())[w]) for f in ref)
        j = min(n, vse_var[w]) - ok
        celkem += n
        spravne += ok
        jinde += j
        if j and len(priklady) < 5:
            kde_ref = [f for f in ref if ref[f][w]]
            kde_var = [f for f in var if var[f][w]]
            priklady.append(f"{w}: značky={kde_ref}, md={kde_var}")
    return {"slov": celkem, "spravne": spravne, "jina_frekvence": jinde,
            "chybi": celkem - spravne - jinde, "priklady": priklady}


# --- 3) falešné nadpisy -------------------------------------------------------
def zvyraznene_radky(pdf: Path) -> set[str]:
    """Řádky PDF, které jsou tučně, kurzívou nebo PODTRŽENÉ (čára pod textem –
    tak bývají v SPC podnadpisy skupin: „Dospělí", „Pediatrické použití")."""
    import pymupdf

    ven = set()
    with pymupdf.open(str(pdf)) as d:
        for p in d:
            cary = [g["rect"] for g in p.get_drawings()
                    if g["rect"].height < 1.5 and g["rect"].width > 10]
            for b in p.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    spany = [s for s in l["spans"] if s["text"].strip()]
                    if not spany:
                        continue
                    styl = all(s["flags"] & (16 | 2) or "Bold" in s["font"]
                               or "Italic" in s["font"] for s in spany)
                    x0, _, x1, y1 = l["bbox"]
                    podtr = any(abs(c.y0 - y1) < 3 and c.x0 < x1 and c.x1 > x0 for c in cary)
                    if styl or podtr:
                        ven.add(cisty("".join(s["text"] for s in spany)).lower().rstrip(":. "))
    return ven


def falesne_nadpisy(md: str, zvyraznene: set[str]) -> list[str]:
    """Nadpisy `##` v sekcích 4.1 a 4.3, které v PDF zvýrazněné NEJSOU."""
    ven = []
    for od in ("4.1", "4.3"):
        for r in _sekce_md(md, od).splitlines():
            if r.startswith("#"):
                t = cisty(r).lower().rstrip(":. ")
                if t and t != "souhrn údajů o přípravku" and t not in zvyraznene:
                    ven.append(t[:60])
    return ven


# --- souhrn ---------------------------------------------------------------------
PRAH_POKRYTI = 0.90


def zkontroluj(md: str, pdf: Path, surovy_text: str, strana_48: int | None,
               pdf_original: Path | None = None) -> dict:
    """Všechny kontroly + verdikt `ok` / `podezreni` s důvody.

    `pdf` = co šlo do převodu (může být oříznuté), `pdf_original` = kvůli
    značkám (ořez je zahodí). Frekvence se ověřují PROTI ZNAČKÁM, když je
    PDF má; jinak geometrií tabulky (find_tables).
    """
    # Pokrytí Markdownu má smysl JEN tam, kde ho extrakce opravdu použije.
    # common/sekce.py bere sekci NÚ z Doclingu jen s TABULKOU; bez ní ze
    # surového textu PDF (zachovává řádky – formát „Orgánová třída:" /
    # „Časté: …"). STOPTUSSIN: Docling udělal z nadpisu 4.8 odrážku, pokrytí
    # vyšlo 0 %, ale extrakce vzala celou sekci ze surového textu – falešný
    # poplach (21 takových SPC, 25. 9.).
    from common.sekce import _ma_tabulku
    md48 = _sekce_md(md, "4.8")
    ze_suroveho = not (md48 and _ma_tabulku(md48))
    pk = None if ze_suroveho else pokryti_48(md, surovy_text)
    zn = frekvence_proti_znackam(md, pdf_original or pdf)
    if zn is not None:
        sl = {"metoda": "znacky", **zn}
    else:
        sl = {"metoda": "geometrie",
              **(sloupce_frekvenci(md, pdf, strana_48) if strana_48 else {"bunek": 0})}
    fn = falesne_nadpisy(md, zvyraznene_radky(pdf))
    duvody = []
    if ze_suroveho:
        if not _sekce_pdf(surovy_text, "4.8"):
            duvody.append("4.8 nenalezena ani v PDF")
    elif pk is None:
        duvody.append("4.8 v PDF nenalezena")
    elif pk < PRAH_POKRYTI:
        duvody.append(f"pokrytí 4.8 {pk:.0%}")
    if sl["metoda"] == "znacky":
        # Na 54 tagovaných SPC dal Docling pod jinou frekvenci 1 slovo
        # z 1 488 – práh 3 slova a 2 % odfiltruje jednotlivé úlomky.
        if sl["jina_frekvence"] >= 3 and sl["jina_frekvence"] > 0.02 * sl["slov"]:
            duvody.append(f"frekvence proti značkám jinde {sl['jina_frekvence']}/{sl['slov']} slov")
    elif sl.get("spatne"):
        duvody.append(f"frekvence ve špatném sloupci {sl['spatne']}/{sl['overeno']}")
    return {"pokryti_48": None if pk is None else round(pk, 3),
            "zdroj_48": "pymupdf_raw" if ze_suroveho else "docling_md",
            "sloupce": sl, "falesne_nadpisy": fn,
            "verdikt": "podezreni" if duvody else "ok", "duvody": duvody}


def strana_sekce(surovy_po_strankach: list[str], cislo: str) -> int | None:
    """Číslo strany (1-based), kde začíná sekce `cislo`."""
    vzor = re.compile(rf"(?m)^\s*{re.escape(cislo)}\.?(\s+\S|\s*$)")
    for i, t in enumerate(surovy_po_strankach, 1):
        if vzor.search(t):
            return i
    return None
