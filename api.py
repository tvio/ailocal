#!/usr/bin/env python3
"""REST API nad hledanim v SPC. Dokumentace na /docs.

Spusteni:
    uv run uvicorn api:app --reload --port 8000
    -> aplikace  http://localhost:8000/
    -> Swagger   http://localhost:8000/docs

POZOR NA START: generativni model ma 87 GB a Ollama ho po ~5 minutach
necinnosti odlozi. Nahrava se proto na POZADI hned pri startu aplikace,
ne az u prvniho dotazu uzivatele - jinak prvni navstevnik ceka minutu
a nevi proc. Stav se da cist z /api/stav, dokud neni `pripraveno`,
frontend ukazuje "aplikace startuje".
"""

import logging
import threading
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common import dotazy
from common.config import PG_DSN, MODEL_ROUTER, MODEL_EMBED
from common.hledani import hledej, seskup, Filtr
from common.router import rozhodni, VSECHNY_SEKCE
from common.ollama_client import priprav_modely

logger = logging.getLogger(__name__)

NA_STRANCE = 10

# Sloupce, podle kterych jde radit. Whitelist, ne volny vstup - jde to
# primo do ORDER BY.
RAZENI = {
    "nazev": "l.nazev",
    "kod_sukl": "l.kod_sukl",
    "sila": "l.sila",
    "atc": "l.atc",
    "na_predpis": "l.na_predpis",
    "hrazeno": "l.hrazeno",
    "ucinne_latky": "l.ucinne_latky",
}

NAZEV_SEKCE = {
    "indikace": "Terapeutické indikace",
    "kontraindikace": "Kontraindikace",
    "nezadouci_ucinky": "Nežádoucí účinky",
    "davkovani": "Dávkování a způsob podání",
    "atributy": "identita léku (z API SÚKL)",
}

app = FastAPI(
    title="localsemantic – hledání v SPC",
    version="1.0",
    description=(
        "Sémantické hledání v souhrnech údajů o přípravku (SPC) ze SÚKL.\n\n"
        "Dotaz projde **routerem** (vytáhne filtry a text pro vektor), pak se "
        "hledá **hybridně** – kosinová podobnost nad embeddingy `bge-m3` "
        "a český fulltext, spojené přes RRF.\n\n"
        "Vše běží lokálně."
    ),
)


# ---------------------------------------------------------------------------
# Stav nahravani modelu
# ---------------------------------------------------------------------------
class StavAplikace(BaseModel):
    pripraveno: bool = Field(description="Jsou modely v pameti a lze hledat?")
    hlaska: str = Field(description="Co se prave deje, pro uzivatele")
    modely: dict[str, str] = Field(default_factory=dict)


_stav = {"pripraveno": False,
         "hlaska": "aplikace startuje (model se načítá do paměti)",
         "modely": {}}


def _nahraj_modely() -> None:
    try:
        for st in priprav_modely((MODEL_ROUTER, MODEL_EMBED)):
            _stav["modely"][st.model] = (
                st.chyba if not st.ok
                else ("byl v paměti" if not st.nacital_se
                      else f"načten za {st.trvalo_s:.1f} s"))
    except Exception as e:                       # síť, Ollama mimo…
        _stav["hlaska"] = f"model se nepodařilo načíst: {e}"
        logger.exception("nahravani modelu selhalo")
        return
    _stav["pripraveno"] = True
    _stav["hlaska"] = "připraveno"


@app.on_event("startup")
def _start() -> None:
    threading.Thread(target=_nahraj_modely, daemon=True).start()


@app.get("/api/stav", response_model=StavAplikace, tags=["stav"],
         summary="Jsou modely nahrané?")
def stav() -> StavAplikace:
    """Frontend se ptá při startu a dokud `pripraveno` není `true`,
    ukazuje přesýpací hodiny s hláškou. Bez toho by první dotaz vypadal
    jako zaseknutá aplikace."""
    return StavAplikace(**_stav)


# ---------------------------------------------------------------------------
# Modely odpovedi
# ---------------------------------------------------------------------------
class Lecivo(BaseModel):
    kod_sukl: str
    nazev: str
    sila: str | None = None
    lekova_forma: str | None = None
    atc: str | None = None
    na_predpis: bool | None = None
    hrazeno: bool | None = None
    ucinne_latky: list[str] = Field(default_factory=list)
    ma_pdf: bool = False
    vek_od: float | None = Field(None, description="od kolika let lze lék použít "
                                 "(odvozeno z SPC 4.1–4.3, common/vek.py); null = nejde určit")
    pro_deti: bool | None = Field(None, description="SPC uvádí dávkování pro děti; null = nevím")


class Nalez(BaseModel):
    """Jedna nalezena pasaz. U vypisu bez hledani je vetsina poli prazdna."""
    sekce: str | None = None
    sekce_nazev: str | None = None
    obsah_text: str | None = None
    frekvence: str | None = None
    organovy_system: str | None = None
    skupina: str | None = None
    strana_pdf: int | None = None
    cosine: float | None = None
    fts: float | None = None
    poradi_sem: int | None = None
    poradi_fts: int | None = None
    rrf: float | None = None
    polozka: dict | None = Field(
        None, description="strukturovana polozka z extrakce (u davkovani pacient, "
                          "davka, frekvence, poznamka) - GUI z ni kresli tabulku")


class Radek(BaseModel):
    lecivo: Lecivo
    skore: float | None = Field(None, description="RRF skore; None u vypisu bez hledani")
    odstup: float | None = Field(None, description="0-100 vuci nejlepsimu")
    nejlepsi: Nalez | None = None
    dalsi: list[Nalez] = Field(default_factory=list)


class Router(BaseModel):
    sekce: list[str] | None = None
    dotaz_text: str | None = None
    jistota: str | None = None
    filtr_popis: str | None = None
    sekce_vynucena: bool = False


class Odpoved(BaseModel):
    dotaz: str | None = None
    router: Router | None = None
    celkem: int
    strana: int
    na_strance: int
    stran: int
    radky: list[Radek]
    prah: float | None = None
    kandidatu_pred_prahem: int | None = None
    usek_orezan: bool = Field(
        False,
        description=("true = cteni sekce, ale zuzil ji jeste dalsi filtr "
                     "(frekvence, skupina pacientu, organovy system), takze "
                     "to NENI cela sekce"))
    cely_usek: bool = Field(
        False,
        description=("true = uzivatel jmenoval konkretni lek A konkretni sekci, "
                     "takze se vraci CELA sekce v poradi dokumentu, ne serazeny "
                     "vyber. Razeni podle podobnosti tam nema co merit."))
    vyber_filtrem: bool = Field(
        False,
        description=("true = dotaz obsahoval jen atributy leku (nazev, ucinna latka, "
                     "kod, sila, ATC) a zadny priznak. Leky vybral SQL filtr nad "
                     "registrem; cosine a fulltext se pocitaji nad radkem identity "
                     "leku, urcuji jen poradi a o kvalite nalezu nic nerikaji - GUI "
                     "je neukazuje."))
    atc_navrh: list[Lecivo] = Field(
        default_factory=list,
        description="Zachranna sit podle ATC skupiny - NENI to nalez v SPC")


# ---------------------------------------------------------------------------
# Pomocne
# ---------------------------------------------------------------------------
_MAPA_SPC: dict[str, str] | None = None


def _pdf(kod: str) -> Path | None:
    """PDF k libovolnemu kodu: data/spc/<spc>/spc.pdf pres mapu kod -> SPC."""
    global _MAPA_SPC
    if _MAPA_SPC is None:
        try:
            from naplni_db import mapa_kod_spc
            _MAPA_SPC = mapa_kod_spc()
        except Exception:
            _MAPA_SPC = {}
    spc = _MAPA_SPC.get(kod)
    if spc:
        p = Path("data/spc") / spc / "spc.pdf"
        if p.exists():
            return p
    return None


def _lecivo_z_radku(r: dict) -> Lecivo:
    return Lecivo(
        kod_sukl=r["kod_sukl"], nazev=r["nazev"], sila=r.get("sila"),
        lekova_forma=r.get("lekova_forma"), atc=r.get("atc"),
        na_predpis=r.get("na_predpis"), hrazeno=r.get("hrazeno"),
        ucinne_latky=list(r.get("ucinne_latky") or []),
        ma_pdf=_pdf(r["kod_sukl"]) is not None,
        vek_od=r.get("vek_od"), pro_deti=r.get("pro_deti"))


def _nalez(v) -> Nalez:
    atr = v.sekce_atributy or {}
    return Nalez(
        sekce=v.sekce, sekce_nazev=NAZEV_SEKCE.get(v.sekce, v.sekce),
        obsah_text=v.obsah_text, frekvence=v.frekvence,
        organovy_system=v.organovy_system, skupina=atr.get("skupina"),
        strana_pdf=v.strana_pdf if hasattr(v, "strana_pdf") else None,
        cosine=round(v.cosine, 4), fts=round(v.fts, 4),
        poradi_sem=v.poradi_sem, poradi_fts=v.poradi_fts,
        rrf=round(v.rrf, 6),
        polozka=atr if v.sekce == "davkovani" and atr else None)


# ---------------------------------------------------------------------------
# Vypis leciv (uvodni obrazovka)
# ---------------------------------------------------------------------------
@app.get("/api/leciva", response_model=Odpoved, tags=["léčiva"],
         summary="Výpis léčiv v korpusu, stránkovaný a řaditelný")
def leciva(
    strana: int = Query(1, ge=1),
    razeni: str = Query("nazev", description=f"jeden z: {', '.join(RAZENI)}"),
    smer: str = Query("asc", pattern="^(asc|desc)$"),
    na_predpis: bool | None = Query(None, description="true = Rx, false = OTC"),
    hrazeno: bool | None = None,
    na_strance: int = Query(NA_STRANCE, ge=5, le=200,
                            description="kolik léčiv na stránku (GUI: 10/25/50/100)"),
) -> Odpoved:
    """Uvodni prehled — bez hledani, takze radky nemaji skore ani poradi.

    Zamerne vraci TYZ tvar jako /api/hledat, aby frontend kreslil jednu
    komponentu. Pole z hledani (`cosine`, `rrf`, ...) jsou proste `null`.
    """
    if razeni not in RAZENI:
        raise HTTPException(400, f"radit lze jen podle: {', '.join(RAZENI)}")

    # Jen zastupci SPC - ostatni baleni tehoz SPC nemaji vlastni extrakci
    # (viz leciva.zastupce v init-db.sql). coalesce kvuli DB bez sloupce hodnot.
    kde, par = ["coalesce(zastupce, true)"], {}
    if na_predpis is not None:
        kde.append("na_predpis = %(np)s")
        par["np"] = na_predpis
    if hrazeno is not None:
        kde.append("hrazeno = %(hr)s")
        par["hr"] = hrazeno
    podminka = f"WHERE {' AND '.join(kde)}" if kde else ""

    par["limit"] = na_strance
    par["offset"] = (strana - 1) * na_strance
    with psycopg.connect(PG_DSN) as c, c.cursor() as cur:
        celkem = cur.execute(
            f"SELECT count(*) FROM leciva l {podminka}", par).fetchone()[0]
        cur.execute(f"""
            SELECT l.kod_sukl, l.nazev, l.sila, l.lekova_forma, l.atc,
                   l.na_predpis, l.hrazeno, l.ucinne_latky, l.vek_od, l.pro_deti
            FROM leciva l {podminka}
            ORDER BY {RAZENI[razeni]} {smer.upper()} NULLS LAST, l.nazev
            LIMIT %(limit)s OFFSET %(offset)s
        """, par)
        sloupce = [d.name for d in cur.description]
        radky = [dict(zip(sloupce, r)) for r in cur.fetchall()]

    return Odpoved(
        celkem=celkem, strana=strana, na_strance=na_strance,
        stran=max(1, -(-celkem // na_strance)),
        radky=[Radek(lecivo=_lecivo_z_radku(r)) for r in radky])


# ---------------------------------------------------------------------------
# Hledani
# ---------------------------------------------------------------------------
@app.get("/api/hledat", response_model=Odpoved, tags=["hledání"],
         summary="Sémantické hledání v SPC")
def hledat(
    q: str = Query(..., min_length=2, description="dotaz běžnou češtinou"),
    sekce: str | None = Query(
        None,
        description=("VYNUTIT sekci a přebít router. Jen jedna. "
                     f"Jedna z: {', '.join(VSECHNY_SEKCE)}")),
    strana: int = Query(1, ge=1),
    prah: float = Query(0.60, ge=0.0, le=1.0),
    leciv: int = Query(50, ge=1, le=200, description="kolik léčiv celkem hledat"),
    pasazi: int = Query(3, ge=1, le=10, description="pasáží na léčivo"),
    na_strance: int = Query(NA_STRANCE, ge=5, le=200,
                            description="kolik léčiv na stránku (GUI: 10/25/50/100)"),
) -> Odpoved:
    """Dotaz projde routerem, ten vytáhne filtry a text pro vektor.

    **`sekce` router PŘEBÍJÍ.** Omezení ale platí jen na sekční výstupy —
    filtry z dotazu (volně prodejný, hrazený, účinná látka, síla) se
    uplatní dál a základní údaje o léčivu se vracejí vždycky.
    """
    if not _stav["pripraveno"]:
        raise HTTPException(503, _stav["hlaska"])
    if sekce and sekce not in VSECHNY_SEKCE:
        raise HTTPException(400, f"neznámá sekce {sekce!r}")

    filtr, jistota, syrove = rozhodni(q)
    vynuceno = False
    if sekce:
        filtr.sekce = [sekce]
        vynuceno = True

    o = hledej(syrove.get("dotaz_text") or q, filtr=filtr,
               limit=leciv * pasazi + 40, prah=prah, puvodni_dotaz=q)
    # U cteni sekce se pasaze NEOREZAVAJI - cilem je ukazat ji celou.
    from common.hledani import je_abecedne
    skupiny = seskup(o.vysledky, leciv=leciv, abecedne=je_abecedne(filtr),
                     pasazi_na_lecivo=200 if o.cely_usek else pasazi)

    nejlepsi_skore = skupiny[0].skore if skupiny else 0.0
    vsechny: list[Radek] = []
    for sk in skupiny:
        v = sk.nejlepsi
        vsechny.append(Radek(
            lecivo=Lecivo(
                kod_sukl=sk.kod_sukl, nazev=sk.nazev, sila=sk.sila,
                lekova_forma=v.lekova_forma, atc=v.atc,
                na_predpis=v.na_predpis, hrazeno=v.hrazeno,
                ucinne_latky=list(v.ucinne_latky or []),
                ma_pdf=_pdf(sk.kod_sukl) is not None,
                vek_od=v.vek_od, pro_deti=v.pro_deti),
            skore=round(sk.skore, 6),
            odstup=round(100.0 * sk.skore / nejlepsi_skore, 1) if nejlepsi_skore else None,
            nejlepsi=_nalez(v),
            dalsi=[_nalez(x) for x in sk.dalsi]))

    celkem = len(vsechny)
    od = (strana - 1) * na_strance
    return Odpoved(
        dotaz=q,
        router=Router(sekce=filtr.sekce, dotaz_text=syrove.get("dotaz_text"),
                      jistota=jistota, filtr_popis=filtr.popis() or None,
                      sekce_vynucena=vynuceno),
        celkem=celkem, strana=strana, na_strance=na_strance,
        stran=max(1, -(-celkem // na_strance)),
        radky=vsechny[od:od + na_strance],
        prah=o.prah, kandidatu_pred_prahem=o.kandidatu_pred_prahem,
        cely_usek=o.cely_usek, usek_orezan=o.usek_orezan,
        vyber_filtrem=bool(filtr.je_presny() and not o.cely_usek and o.vysledky
                           and all(v.sekce == "atributy" for v in o.vysledky)),
        atc_navrh=_atc_navrh(syrove.get("dotaz_text") or q, filtr) if not vsechny else [])


def _atc_navrh(dotaz: str, filtr: Filtr) -> list[Lecivo]:
    """Zachranna sit: kdyz se nenaslo nic, nabidnout terapeutickou skupinu.

    NENI to nalez v SPC, je to odvozeni z ATC skupiny prirazene SUKLem -
    frontend to musi zobrazit oddelene a oznacene. Filtr uzivatele plati
    i tady, jinak by na "hrazene antibiotikum" vyskocil nehrazeny lek.
    """
    from common.dotazy import atc_pro_dotaz

    prefixy = atc_pro_dotaz(dotaz)
    if not prefixy:
        return []
    kde, par = ["atc LIKE %(atc)s"], {}
    if filtr.na_predpis is not None:
        kde.append("na_predpis = %(np)s")
        par["np"] = filtr.na_predpis
    if filtr.hrazeno is not None:
        kde.append("hrazeno = %(hr)s")
        par["hr"] = filtr.hrazeno

    ven: list[Lecivo] = []
    with psycopg.connect(PG_DSN) as c, c.cursor() as cur:
        for atc in prefixy:
            par["atc"] = atc + "%"
            cur.execute(f"""
                SELECT kod_sukl, nazev, sila, lekova_forma, atc,
                       na_predpis, hrazeno, ucinne_latky, vek_od, pro_deti
                FROM leciva WHERE coalesce(zastupce, true) AND {' AND '.join(kde)} ORDER BY nazev
            """, par)
            sl = [d.name for d in cur.description]
            ven += [_lecivo_z_radku(dict(zip(sl, r))) for r in cur.fetchall()]
    return ven


class PolozkaSekce(BaseModel):
    obsah_text: str
    skupina: str | None = None
    frekvence: str | None = None
    organovy_system: str | None = None
    strana_pdf: int | None = None


@app.get("/api/lecivo/{kod_sukl}/sekce/{sekce}", response_model=list[PolozkaSekce],
         tags=["léčiva"], summary="Všechny položky jedné sekce léku v pořadí dokumentu")
def sekce_leciva(kod_sukl: str, sekce: str) -> list[PolozkaSekce]:
    """Pro rozbaleni v GUI: „ostatni indikace leku" pod dalsimi shodami.

    GUI si to nacita LINE az pri rozbaleni radku - aby se odpoved hledani
    nezvetsovala o sekce vsech leku, ktere clovek nikdy nerozbali.
    """
    if sekce not in NAZEV_SEKCE:
        raise HTTPException(400, f"neznámá sekce: {sekce}")
    with psycopg.connect(PG_DSN) as c, c.cursor() as cur:
        cur.execute("""SELECT obsah_text, sekce_atributy, frekvence, organovy_system,
                              strana_pdf
                       FROM leciva_search WHERE kod_sukl = %s AND sekce = %s
                       ORDER BY id""", (kod_sukl, sekce))
        return [PolozkaSekce(obsah_text=t, skupina=(a or {}).get("skupina"),
                             frekvence=f, organovy_system=o, strana_pdf=s)
                for t, a, f, o, s in cur.fetchall()]


@app.get("/api/pdf/{kod_sukl}", tags=["léčiva"],
         summary="SPC v PDF, volitelně otevřené na konkrétní straně")
def pdf(kod_sukl: str, strana: int | None = None):
    """Vrací původní PDF ze SÚKL. `strana` se předává prohlížeči
    fragmentem `#page=N`, takže se otevře rovnou u nalezené pasáže."""
    p = _pdf(kod_sukl)
    if not p:
        raise HTTPException(404, f"PDF pro {kod_sukl} není k dispozici")
    return FileResponse(p, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{p.name}"'})


# ---------------------------------------------------------------------------
# Hledaci slovnik (slovnik_dotazu.json) - prohlizeni a uprava z GUI
# ---------------------------------------------------------------------------
# Slovnik rozsiruje DOTAZ (common/dotazy.py): vyraz uzivatele -> formulace,
# ktera v datech opravdu je. Vymyslena formulace nenajde nic, proto se pri
# pridani overuje proti zjednodusenym indikacim v DB a bez shody se neulozi.
#
# Uloziste je tabulka slovnik_dotazu (ne soubor): spolecna vsem instancim
# API a cte se pri kazdem hledani, takze zmena plati hned a vsude.
_HTTP_SLOVNIK = {"neplatne": 422, "duplicita": 409, "plno": 409, "neni": 404}


class PolozkaSlovniku(BaseModel):
    vyraz: str = Field(description="Co píše uživatel (kmen slova)")
    formulace: list[str] = Field(description="Formulace z indikací, které se přihledají")


class NavrhFormulace(BaseModel):
    text: str = Field(description="Zjednodušená indikace tak, jak je v datech")
    leciv: int = Field(description="U kolika léků se vyskytuje")


class NovaPolozkaSlovniku(BaseModel):
    vyraz: str
    formulace: list[str] | str = Field(
        description="Jedna nebo víc formulací (nejvýš 4 na výraz); uloží se všechny, nebo žádná")


def _slovnik_vypis() -> list[PolozkaSlovniku]:
    return [PolozkaSlovniku(vyraz=v, formulace=f) for v, f in dotazy.vypis()]


def _formulace_v_datech(text: str, limit: int = 10) -> list[NavrhFormulace]:
    """Zjednodusene indikace, ktere `text` obsahuji, nejcastejsi napred."""
    vzor = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with psycopg.connect(PG_DSN) as c, c.cursor() as cur:
        cur.execute("""SELECT lower(sekce_atributy->>'laicky') AS t,
                              count(DISTINCT kod_sukl) AS n
                       FROM leciva_search
                       WHERE sekce = 'indikace' AND sekce_atributy->>'laicky' ILIKE %s
                       GROUP BY 1 ORDER BY n DESC, length(lower(sekce_atributy->>'laicky'))
                       LIMIT %s""", (vzor, limit))
        return [NavrhFormulace(text=t, leciv=n) for t, n in cur.fetchall()]


@app.get("/api/slovnik", response_model=list[PolozkaSlovniku], tags=["slovník"],
         summary="Hledací slovník: výraz uživatele → formulace v indikacích")
def slovnik() -> list[PolozkaSlovniku]:
    """Naposledy upravený výraz je první."""
    return _slovnik_vypis()


@app.get("/api/slovnik/formulace", response_model=list[NavrhFormulace], tags=["slovník"],
         summary="Které zjednodušené indikace v datech obsahují daný text")
def slovnik_formulace(q: str = Query(min_length=3, max_length=100)) -> list[NavrhFormulace]:
    return _formulace_v_datech(q.strip())


@app.post("/api/slovnik", response_model=list[PolozkaSlovniku], tags=["slovník"],
          summary="Přidat výraz a jednu či víc formulací (každá musí být v datech)")
def slovnik_pridej(p: NovaPolozkaSlovniku) -> list[PolozkaSlovniku]:
    formulace = dotazy.cisti_formulace(p.formulace)
    for f in formulace:
        if len(f) >= 3 and not _formulace_v_datech(f, limit=1):
            raise HTTPException(422, f"Formulace „{f}“ se v indikacích žádného léku "
                                     "nevyskytuje, hledání by nic nenašlo. Vyberte z nabídky.")
    try:
        dotazy.pridej(p.vyraz, formulace)
    except dotazy.ChybaSlovniku as e:
        raise HTTPException(_HTTP_SLOVNIK[e.kod], str(e))
    return _slovnik_vypis()


@app.delete("/api/slovnik", response_model=list[PolozkaSlovniku], tags=["slovník"],
            summary="Odebrat jednu formulaci u výrazu")
def slovnik_odeber(vyraz: str, formulace: str) -> list[PolozkaSlovniku]:
    try:
        dotazy.odeber(vyraz, formulace)
    except dotazy.ChybaSlovniku as e:
        raise HTTPException(_HTTP_SLOVNIK[e.kod], str(e))
    return _slovnik_vypis()


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
