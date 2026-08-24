"""Router: z dotazu v prirozene reci udela FILTR a vyber SEKCI.

Proc to je potreba: bez routeru vrati dotaz "volne prodejny lek na bolest"
polozky ze sekce nezadouci_ucinky - tedy leky, ktere bolest ZPUSOBUJI,
ne ktere ji leci. U aplikace pro laiky je to nebezpecna zamena.

Pravidla ze zadani, ktera musi router dodrzet:

  1. Kdyz uzivatel jasne nerekne sekci, symptom je VZDY INDIKACE.
     "po prasicich me boli bricho" -> hleda se lek na bolest bricha,
     ne lek, ktery bolest bricha zpusobuje.
  2. Kdyz v dotazu neni nic o filtru, filtr se NEPOUZIJE. Nedomyslet si.
  3. Kdyz si router neni jisty, hleda se ve VSECH sekcich a u kazdeho
     vysledku se ukaze, odkud pochazi.

Router je zamerne uzka uloha s malym vystupem - jen filtr a sekce,
zadne prepisovani dotazu. Kratky vystup = rychla odpoved.
"""

import json
import unicodedata
import logging

from common.config import MODEL_ROUTER
from common.hledani import Filtr

logger = logging.getLogger(__name__)

SYSTEM = (
    "Jsi router vyhledávání v databázi léčiv. Z dotazu uživatele určíš, "
    "ve které sekci se má hledat a jaké filtry použít. "
    "Nic nevymýšlíš a dotaz nepřepisuješ. "
    "Vrať POUZE validní JSON, žádný jiný text."
)

POKYN = """Urči, kde se má hledat a čím se má omezit.

Vrať JSON:
{
  "sekce": ["indikace"],        // kde hledat, viz níž
  "dotaz_text": "bolest",       // JEN zbytek pro sémantiku, viz níž
  "na_predpis": null,           // true = jen na předpis, false = jen volně
  "hrazeno": null,              // true = jen hrazené pojišťovnou, false = jen nehrazené
  "frekvence": null,            // PŘESNÁ frekvence nežádoucího účinku, viz níž
                                // prodejné, null = neomezovat
  "sila": null,                 // "500MG" bez mezery, nebo null
  "organovy_system": null,      // MedDRA třída, nebo null
  "frekvence_rank_max": null,   // 1=velmi časté, 2=časté ... 9=není známo
  "nazev": null,                // uživatel jmenoval konkrétní lék
  "kod_sukl": null,             // 7místný kód, když ho uvedl
  "ucinna_latka": null,         // "paracetamol", nebo null
  "atc_prefix": null,           // "N02", nebo null
  "jistota": "vysoka"           // vysoka | nizka
}

SEKCE, ze kterých se vybírá:
- "indikace"         na co se lék používá (nemoc, příznak)
- "nezadouci_ucinky" co lék může způsobit
- "kontraindikace"   kdy se lék nesmí užívat
- "davkovani"        kolik a jak často
- "atributy"         identita léku: název, síla, účinná látka

DOTAZ_TEXT je KLÍČOVÝ:
Je to jen ta část dotazu, která se má hledat SÉMANTICKY – tedy to,
co po vytažení filtrů zbude. Ne celá věta.
  "volně prodejný lék na bolest se silou 500mg" -> dotaz_text: "bolest"
  "co dělá Paralen se srdcem"                   -> dotaz_text: "srdce"
Slova jako "najdi mi", "nějaké", "lék na", "volně prodejný", "500mg",
"nežádoucí účinek" do dotaz_textu NEPATŘÍ – buď jsou to filtry, nebo vata.

VYNECH I SLOVA "léčba", "léčení", "terapie", "přípravek", "prostředek".
Jsou skoro v každé indikaci, takže dotaz na ně navléká podobnost na
všechno. "léčba roztroušené sklerózy" -> dotaz_text: "roztroušená skleróza"

ALE: název nemoci nebo příznaku nech CELÝ a v podobě, v jaké ho uživatel
napsal. Nezkracuj ho na jedno slovo a nepřepisuj do jiného tvaru.
  "Bolest břicha nežádoucí účinek" -> dotaz_text: "bolest břicha"
                                      (NE "břicho" – ztratí se "bolest")
  "co dělá lék se srdcem"          -> dotaz_text: "srdce"
                                      (tady je "srdce" celý pojem)

PIŠ ČESKY S DIAKRITIKOU. Nikdy nepřepisuj do ASCII.
Vyhledávání je na diakritiku citlivé a její ztráta stojí zhruba pětinu
podobnosti - "kasel" místo "kašel" najde úplně jiný lék.
  "zácpa" (NE "zacpa"), "kašel" (NE "kasel"), "ucpaný nos" (NE "ucpany nos")
Když uživatel napíše bez diakritiky, ty ji do dotaz_textu DOPLŇ.

ZÁPOR JE SOUČÁST PŘÍZNAKU a nesmí se zahodit. "nemůžu spát" je nespavost,
kdežto samotné "spát" neznamená nic – holé sloveso je podobné spoustě
nesouvisejících příznaků a výsledky se slijí dohromady.
  "nemůžu po prášcích spát"  -> dotaz_text: "nemůžu spát"   (NE "spát")
  "nemůžu dýchat nosem"      -> dotaz_text: "nemůžu dýchat nosem"
  "nechce se mi jíst"        -> dotaz_text: "nechce se mi jíst"

DOTAZ_TEXT MUSÍ DÁVAT SMYSL SÁM O SOBĚ. Když se na něj podíváš bez
původní věty a nepoznáš, co člověk hledá, ořezal jsi moc.
Když po vytažení filtrů nezbude nic (dotaz je jen název léku),
dej do dotaz_text ten název.

NEJDŮLEŽITĚJŠÍ PRAVIDLO:
Když uživatel NEŘEKNE výslovně, že jde o nežádoucí účinek, je příznak
VŽDY INDIKACE. "bolí mě břicho" = hledá lék NA bolest břicha, ne lék,
který bolest břicha způsobuje.
Sekci "nezadouci_ucinky" zvol JEN tehdy, když dotaz mluví o tom, že
potíže způsobil LÉK. Musí tam být něco jako "nežádoucí účinek",
"vedlejší účinek", "co ten lék způsobuje", "po tom léku mi je".
Samotné "po něčem mi je" NESTAČÍ – jídlo, počasí ani nemoc nejsou lék.

VÝJIMKA – KONKRÉTNÍ LÉK + PŘÍZNAK BEZ URČENÍ SMĚRU:
Když dotaz jmenuje KONKRÉTNÍ lék a k němu příznak, ale neřekne, jestli
ho lék léčí, nebo způsobuje, dej do sekce OBĚ – ["indikace",
"nezadouci_ucinky"] – a jistotu "nizka".
Z takového dotazu totiž směr POZNAT NELZE, stejný tvar věty má obě čtení:
  "paralen bolest hlavy"   – bolest hlavy Paralen LÉČÍ    (indikace)
  "paralen bolest břicha"  – bolest břicha lék ZPŮSOBUJE  (nežádoucí)
Rozhoduje to, co je o tom léku v datech, ne jak je dotaz napsaný. Filtr
na název zúží výběr na jeden lék, takže obě sekce jsou pár desítek
položek a správnou vybere podobnost sama.
Tohle platí JEN když je lék jmenován. Bez léku ("bolí mě břicho") dál
platí pravidlo výš – je to indikace, člověk hledá, co si vzít.

DALŠÍ PRAVIDLA:
- Když v dotazu není nic o filtru, nech filtr null. Nedomýšlej si.
- "volně prodejný", "bez předpisu", "bez receptu" -> na_predpis: false
- "na předpis", "na recept" -> na_predpis: true
FREKVENCE NEŽÁDOUCÍCH ÚČINKŮ. Když uživatel řekne, jak často se účinek
vyskytuje, vyplň `frekvence` PŘESNĚ jednou z těchto šesti hodnot:
  "velmi časté", "časté", "méně časté", "vzácné", "velmi vzácné", "není známo"

  "velmi časté nežádoucí účinky"  -> frekvence: "velmi časté"
  "vzácné vedlejší účinky"        -> frekvence: "vzácné"
  "co se stává vzácně"            -> frekvence: "vzácné"

POZOR: "vzácné" znamená VZÁCNÉ, ne "vzácné a všechno častější". Kdo se
ptá na vzácné účinky, nechce vidět ty velmi časté.
`frekvence_rank_max` použij JEN u výslovného "a častější"
("časté a častější" -> frekvence_rank_max: 2), jinak ho nech null.

- "hrazený", "hrazené", "na pojišťovnu", "platí pojišťovna", "z pojištění"
  -> hrazeno: true
- "nehrazený", "doplácí se", "za plnou cenu", "si platím sám" -> hrazeno: false

POZOR: HRAZENOST A ZPŮSOB VÝDEJE JSOU DVĚ RŮZNÉ VĚCI a nesmí se plést.
Lék může být na předpis a přitom nehrazený. Když uživatel mluví
o penězích a pojišťovně, je to `hrazeno`, ne `na_predpis`.
  "hrazené antibiotikum"       -> hrazeno: true,  na_predpis: null
  "volně prodejný lék"         -> hrazeno: null,  na_predpis: false
  "hrazený lék na předpis"     -> hrazeno: true,  na_predpis: true
- Sílu piš BEZ mezery velkými písmeny: "500 mg" -> "500MG"
- Když si nejsi jistý sekcí, dej jistota "nizka" a do sekce dej VŠECHNY,
  které přicházejí v úvahu. Lepší hledat šíř než minout.

PŘÍKLADY:
"najdi mi volně prodejné léky na bolest"
  -> {"sekce":["indikace"],"dotaz_text":"bolest","na_predpis":false,
      "sila":null,"organovy_system":null,"frekvence_rank_max":null,
      "nazev":null,"kod_sukl":null,"ucinna_latka":null,"atc_prefix":null,
      "jistota":"vysoka"}
"volně prodejný lék na bolest se silou 500mg"
  -> {"sekce":["indikace"],"dotaz_text":"bolest","na_predpis":false,
      "sila":"500MG","organovy_system":null,"frekvence_rank_max":null,
      "nazev":null,"kod_sukl":null,"ucinna_latka":null,"atc_prefix":null,
      "jistota":"vysoka"}
"bolest břicha nežádoucí účinek"
  -> {"sekce":["nezadouci_ucinky"],"na_predpis":null,"sila":null,
      "organovy_system":null,"frekvence_rank_max":null,"jistota":"vysoka"}
"po prasecim co jsem si vzal me boli bricho"
  -> {"sekce":["indikace"],"na_predpis":null,"sila":null,
      "organovy_system":null,"frekvence_rank_max":null,"jistota":"vysoka"}
  (jidlo neni lek - clovek hleda lek NA bolest bricha)
"paralen bolesti bricha"
  -> {"sekce":["indikace","nezadouci_ucinky"],"nazev":"Paralen",
      "dotaz_text":"bolesti bricha","na_predpis":null,"sila":null,
      "organovy_system":null,"frekvence_rank_max":null,"jistota":"nizka"}
  (konkretni lek + priznak, smer neni receny -> obe sekce)
"po tom leku me boli bricho"
  -> {"sekce":["nezadouci_ucinky"],"na_predpis":null,"sila":null,
      "organovy_system":null,"frekvence_rank_max":null,"jistota":"vysoka"}
"hrazene antibiotikum"
  -> {"sekce":["indikace"],"dotaz_text":"antibiotikum","na_predpis":null,
      "hrazeno":true,"sila":null,"organovy_system":null,
      "frekvence_rank_max":null,"jistota":"vysoka"}
  (hrazenost NENI zpusob vydeje - na_predpis zustava null)
"Paralen 500mg"
  -> {"sekce":["atributy"],"na_predpis":null,"sila":"500MG",
      "organovy_system":null,"frekvence_rank_max":null,"jistota":"vysoka"}
"co dělá ten lék se srdcem"
  -> {"sekce":["nezadouci_ucinky"],"na_predpis":null,"sila":null,
      "organovy_system":"Srdeční poruchy","frekvence_rank_max":null,
      "jistota":"vysoka"}"""

def _frekvence(hodnota) -> str | None:
    """Normalizuje frekvenci na kanonicky tvar z ciselniku.

    Pousti se pres tutez funkci jako extrakce, takze filtr a data mluvi
    stejnym jazykem - kdyby model napsal "Velmi caste", shoda v SQL by
    jinak selhala.
    """
    if not isinstance(hodnota, str) or not hodnota.strip():
        return None
    from common.extrakce import normalizuj_frekvenci

    kanon, _ = normalizuj_frekvenci(hodnota)
    return kanon


def _bez_diakritiky(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def obnov_diakritiku(dotaz_text: str, original: str) -> str:
    """Vrati do dotaz_textu diakritiku podle puvodniho dotazu uzivatele.

    Model ji obcas zahodi ("ucpaný nos" -> "ucpany nos") a je to DRAHE:
    bge-m3 je na diakritiku citlivy, zmereno na indikacich

        'ucpaný nos' -> 0,682     'ucpany nos' -> 0,464
        'zácpa'      -> 0,657     'zacpa'      -> 0,486
        'kašel'      -> 0,591 ACC 'kasel'      -> 0,361 ABAKTAL (jiny lek!)

    Ztrata je ~0,2, tedy dost na propadnuti pod prah. Spolehnout se na
    pokyn v promptu nestaci - tohle je deterministicka zachrana: kdyz se
    slovo po odstraneni diakritiky shoduje se slovem z puvodniho dotazu,
    vezme se tvar UZIVATELE.
    """
    if not dotaz_text or not original:
        return dotaz_text
    mapa = {_bez_diakritiky(w): w for w in original.split() if w}
    ven = []
    for slovo in dotaz_text.split():
        klic = _bez_diakritiky(slovo)
        puvodni = mapa.get(klic)
        # Nahrazuje se JEN kdyz model diakritiku ubral, ne kdyz slovo zmenil.
        if puvodni and puvodni != slovo and _bez_diakritiky(puvodni) == klic:
            ven.append(puvodni)
        else:
            ven.append(slovo)
    return " ".join(ven)


VSECHNY_SEKCE = ["indikace", "nezadouci_ucinky", "kontraindikace",
                 "davkovani", "atributy"]


def rozhodni(dotaz: str, *, model: str = MODEL_ROUTER,
             base_url: str | None = None) -> tuple[Filtr, str, dict]:
    """Vrati (filtr, jistota, surove rozhodnuti).

    Kdyz router selze, vrati prazdny filtr a jistotu 'nizka' - hleda se
    tedy ve vsem. Selhani routeru NESMI shodit hledani.
    """
    from common.extrakce import _ocisti_odpoved
    from common.ollama_client import chat

    prompt = f"{POKYN}\n\n--- DOTAZ ---\n{dotaz}\n--- KONEC ---"
    try:
        odpoved = chat(prompt, system=SYSTEM, model=model,
                       base_url=base_url, json_mode=True)
        d = json.loads(_ocisti_odpoved(odpoved))
    except Exception as e:
        logger.warning("router selhal (%s: %s), hleda se ve vsem",
                       type(e).__name__, e)
        return Filtr(), "nizka", {"chyba": f"{type(e).__name__}: {e}"}

    if not isinstance(d, dict):
        return Filtr(), "nizka", {"chyba": "router nevratil objekt"}

    jistota = str(d.get("jistota") or "nizka").lower()

    sekce = d.get("sekce")
    if isinstance(sekce, str):
        sekce = [sekce]
    if not isinstance(sekce, list) or not sekce:
        sekce, jistota = None, "nizka"
    else:
        # Neznamou sekci zahodit - nesmi se dostat do SQL.
        sekce = [s for s in sekce if s in VSECHNY_SEKCE] or None
        if sekce is None:
            jistota = "nizka"

    # Pri nizke jistote se hleda siroko - ALE kdyz model sam vyjmenoval
    # VIC kandidatu, je ten vycet informace a zahodit ho by bylo skodlive.
    # Prompt o to primo zada ("do sekce dej VSECHNY, ktere prichazeji
    # v uvahu"), takze se drzi. Jedina sekce + nizka jistota si protireci
    # - tam se radeji hleda vsude.
    if jistota == "nizka" and (sekce is None or len(sekce) < 2):
        sekce = None

    sila = d.get("sila")
    if isinstance(sila, str):
        sila = sila.replace(" ", "").upper() or None

    rank = d.get("frekvence_rank_max")
    if not isinstance(rank, int) or not 1 <= rank <= 9:
        rank = None

    def _text(klic):
        v = d.get(klic)
        return v.strip() if isinstance(v, str) and v.strip() else None

    filtr = Filtr(
        nazev=_text("nazev"),
        kod_sukl=_text("kod_sukl"),
        ucinna_latka=_text("ucinna_latka"),
        atc_prefix=_text("atc_prefix"),
        sekce=sekce,
        na_predpis=d.get("na_predpis") if isinstance(d.get("na_predpis"), bool) else None,
        hrazeno=d.get("hrazeno") if isinstance(d.get("hrazeno"), bool) else None,
        frekvence=_frekvence(d.get("frekvence")),
        sila=sila,
        organovy_system=d.get("organovy_system") or None,
        frekvence_rank_max=rank,
    )
    # Dotaz pro semantiku: jen zbytek po vytazeni filtru. Kdyz ho router
    # nevratil nebo je prazdny, pouzije se puvodni dotaz - lepsi hledat
    # nad celou vetou nez nad nicim.
    # Diakritiku model obcas zahodi a stoji to ~0,2 podobnosti,
    # takze se deterministicky vraci podle puvodniho dotazu.
    d["dotaz_text"] = obnov_diakritiku(_text("dotaz_text") or dotaz, dotaz)
    return filtr, jistota, d
