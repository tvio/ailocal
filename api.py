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

from common.config import PG_DSN, MODEL_ROUTER, MODEL_EMBED
from common.hledani import hledej, seskup, Filtr
from common.router import rozhodni, VSECHNY_SEKCE
from common.ollama_client import priprav_modely

logger = logging.getLogger(__name__)

LECIVA_DIR = Path("data/leciva")
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
    atc_navrh: list[Lecivo] = Field(
        default_factory=list,
        description="Zachranna sit podle ATC skupiny - NENI to nalez v SPC")


# ---------------------------------------------------------------------------
# Pomocne
# ---------------------------------------------------------------------------
def _pdf(kod: str) -> Path | None:
    for p in LECIVA_DIR.glob(f"{kod}_*/spc.pdf"):
        return p
    return None


def _lecivo_z_radku(r: dict) -> Lecivo:
    return Lecivo(
        kod_sukl=r["kod_sukl"], nazev=r["nazev"], sila=r.get("sila"),
        lekova_forma=r.get("lekova_forma"), atc=r.get("atc"),
        na_predpis=r.get("na_predpis"), hrazeno=r.get("hrazeno"),
        ucinne_latky=list(r.get("ucinne_latky") or []),
        ma_pdf=_pdf(r["kod_sukl"]) is not None)


def _nalez(v) -> Nalez:
    atr = v.sekce_atributy or {}
    return Nalez(
        sekce=v.sekce, sekce_nazev=NAZEV_SEKCE.get(v.sekce, v.sekce),
        obsah_text=v.obsah_text, frekvence=v.frekvence,
        organovy_system=v.organovy_system, skupina=atr.get("skupina"),
        strana_pdf=v.strana_pdf if hasattr(v, "strana_pdf") else None,
        cosine=round(v.cosine, 4), fts=round(v.fts, 4),
        poradi_sem=v.poradi_sem, poradi_fts=v.poradi_fts,
        rrf=round(v.rrf, 6))


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
) -> Odpoved:
    """Uvodni prehled — bez hledani, takze radky nemaji skore ani poradi.

    Zamerne vraci TYZ tvar jako /api/hledat, aby frontend kreslil jednu
    komponentu. Pole z hledani (`cosine`, `rrf`, ...) jsou proste `null`.
    """
    if razeni not in RAZENI:
        raise HTTPException(400, f"radit lze jen podle: {', '.join(RAZENI)}")

    kde, par = [], {}
    if na_predpis is not None:
        kde.append("na_predpis = %(np)s")
        par["np"] = na_predpis
    if hrazeno is not None:
        kde.append("hrazeno = %(hr)s")
        par["hr"] = hrazeno
    podminka = f"WHERE {' AND '.join(kde)}" if kde else ""

    par["limit"] = NA_STRANCE
    par["offset"] = (strana - 1) * NA_STRANCE
    with psycopg.connect(PG_DSN) as c, c.cursor() as cur:
        celkem = cur.execute(
            f"SELECT count(*) FROM leciva l {podminka}", par).fetchone()[0]
        cur.execute(f"""
            SELECT l.kod_sukl, l.nazev, l.sila, l.lekova_forma, l.atc,
                   l.na_predpis, l.hrazeno, l.ucinne_latky
            FROM leciva l {podminka}
            ORDER BY {RAZENI[razeni]} {smer.upper()} NULLS LAST, l.nazev
            LIMIT %(limit)s OFFSET %(offset)s
        """, par)
        sloupce = [d.name for d in cur.description]
        radky = [dict(zip(sloupce, r)) for r in cur.fetchall()]

    return Odpoved(
        celkem=celkem, strana=strana, na_strance=NA_STRANCE,
        stran=max(1, -(-celkem // NA_STRANCE)),
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
    prah: float = Query(0.55, ge=0.0, le=1.0),
    leciv: int = Query(50, ge=1, le=200, description="kolik léčiv celkem hledat"),
    pasazi: int = Query(3, ge=1, le=10, description="pasáží na léčivo"),
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
               limit=leciv * pasazi + 40, prah=prah)
    # U cteni sekce se pasaze NEOREZAVAJI - cilem je ukazat ji celou.
    skupiny = seskup(o.vysledky, leciv=leciv,
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
                ma_pdf=_pdf(sk.kod_sukl) is not None),
            skore=round(sk.skore, 6),
            odstup=round(100.0 * sk.skore / nejlepsi_skore, 1) if nejlepsi_skore else None,
            nejlepsi=_nalez(v),
            dalsi=[_nalez(x) for x in sk.dalsi]))

    celkem = len(vsechny)
    od = (strana - 1) * NA_STRANCE
    return Odpoved(
        dotaz=q,
        router=Router(sekce=filtr.sekce, dotaz_text=syrove.get("dotaz_text"),
                      jistota=jistota, filtr_popis=filtr.popis() or None,
                      sekce_vynucena=vynuceno),
        celkem=celkem, strana=strana, na_strance=NA_STRANCE,
        stran=max(1, -(-celkem // NA_STRANCE)),
        radky=vsechny[od:od + NA_STRANCE],
        prah=o.prah, kandidatu_pred_prahem=o.kandidatu_pred_prahem,
        cely_usek=o.cely_usek, usek_orezan=o.usek_orezan,
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
                       na_predpis, hrazeno, ucinne_latky
                FROM leciva WHERE {' AND '.join(kde)} ORDER BY nazev
            """, par)
            sl = [d.name for d in cur.description]
            ven += [_lecivo_z_radku(dict(zip(sl, r))) for r in cur.fetchall()]
    return ven


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


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
