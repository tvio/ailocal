"""Krok 3 pipeline: převod textu sekce SPC do strukturovaného JSON.

Prompty vycházejí z legacy/demo04_simplify_text.py, kde se osvědčily
v cloudu. Změny oproti legacy:

  - klíč 'vedlejsi_ucinky' přejmenován na 'nezadouci_ucinky'
    (sjednoceno se zadáním a s hodnotou sloupce leciva_search.sekce)
  - u nežádoucích účinků přibyl 'organovy_system' (MedDRA SOC) –
    ověřeno, že názvy jsou napříč dokumenty doslova shodné, takže z toho
    jde udělat deterministický filtr místo doufání v sémantiku
  - prompt pro nežádoucí účinky popisuje VŠECH PĚT formátů, které se
    v SPC reálně vyskytují (změřeno na 23 dokumentech, viz poznatky.md),
    včetně toho, že se styly střídají i uvnitř jedné sekce
"""

import re
import json
import logging
from dataclasses import dataclass, field

from common.config import MODEL_EXTRAKCE, FREKVENCE_RANK, FREKVENCE_RANK_NEZNAMA
from common.ollama_client import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Jsi asistent pro strukturovanou extrakci informací z farmaceutických SPC dokumentů. "
    "Převádíš odborný text na krátké strukturované položky. "
    "Kde se vyžaduje laický tvar, řekni totéž jednoduchou češtinou bez latiny "
    "a bez odborných slov – tak, aby tomu rozuměl člověk bez lékařského vzdělání. "
    "Nikdy si nic nevymýšlej – piš jen to, co je ve zdrojovém textu. "
    "Vrať POUZE validní JSON, žádný jiný text."
)

# Popis formátů se vkládá do promptu pro nežádoucí účinky. Bez něj model
# zvládne tabulky, ale plete se u dokumentů, kde je frekvence na vlastním
# řádku nebo kde jsou sloupce tabulky frekvence.
POPIS_FORMATU = """\nZdrojový text může mít několik různých podob a v jednom dokumentu se mohou střídat:

1) Tabulka, řádek na účinek:
   | Orgánový systém | Frekvence | Nežádoucí účinek |
   | Poruchy kůže    | vzácné    | vyrážka, kopřivka |

2) Tabulka, kde SLOUPCE jsou frekvence:
   | Velmi časté | Časté | Méně časté |
   Název orgánového systému bývá v řádku přes celou šířku, účinky jsou
   pak v tom sloupci, který odpovídá jejich frekvenci.

3) Frekvence a účinky na jednom řádku:
   Poruchy kůže a podkožní tkáně
   Vzácné: vyrážka, kopřivka

4) Frekvence na vlastním řádku, účinky až na dalším:
   Poruchy kůže a podkožní tkáně:
   Vzácné:
   vyrážka, kopřivka

5) Souvislý text bez struktury (u malých přípravků jen pár vět).

Ve všech případech platí totéž: každý účinek přiřaď k té frekvenci
a tomu orgánovému systému, pod kterými je uvedený ve zdroji.
Když si u konkrétní položky nejsi jistý frekvencí, dej "není známo".
"""

PROMPTY = {
    # Indikace a kontraindikace maji STEJNY tvar jako nezadouci ucinky:
    # dvojice "doslovne ze zdroje" + "laicky". Driv to byl jen laicky
    # retezec, coz melo dva nasledky:
    #   - nebylo co porovnat se zdrojem, takze deterministicka kontrola
    #     tuhle sekci vubec nemohla overit
    #   - limit "2-5 slov" nutil model slucovat a zahazovat polozky
    # Klice jsou 'doslovne' a 'laicky' (ne 'indikace'/'indikace_laicky'),
    # aby se nepletly s nazvem pole, ktere je taky "indikace".
    "indikace": (
        "Z textu sekce indikace vytvoř JSON: {\"indikace\": [{...}]}. "
        "Každý objekt má klíče: doslovne, laicky.\n"
        "- doslovne: JEDNA indikace opsaná ze zdroje DOSLOVA, včetně odborného "
        "termínu. Nezjednodušuj – slouží k ověření proti dokumentu.\n"
        "- laicky: TATÁŽ indikace řečená tak, jak by ji popsal laik, bez latiny "
        "(astma bronchiale → alergické astma, Quinckeho edém → náhlý otok kůže "
        "a sliznic). Když je termín srozumitelný i laikovi, zopakuj ho.\n"
        "\nKAŽDOU indikaci uveď zvlášť, NESLUČUJ je do jedné položky. "
        "Zdroj je často jedna dlouhá věta – projdi ji celou až do konce.\n"
        "\nINDIKACE JE NEMOC NEBO PŘÍZNAK, na který se lék používá. "
        "Do výsledku NEPATŘÍ a musíš je VYNECHAT:\n"
        "- údaje o tom, která síla je pro kterou věkovou skupinu "
        "(\"OLYNTH 0,5 mg/ml: léčba dětí od 2 do 7 let\")\n"
        "- nadpisy skupin pacientů (\"Dospělí\", \"Pediatrické použití\", "
        "\"Děti od 4 let a dospívající\")\n"
        "- údaje o tom, jestli je lék na předpis "
        "(\"Léčba bez porady s lékařem:\")\n"
        "Nadpis NIKDY nespojuj s položkou pod ním do jedné indikace. "
        "Když pod nadpisem skupiny pacientů je nemoc, uveď jen tu nemoc "
        "a skupinu zapiš do klíče 'skupina'.\n"
        "- skupina: pro koho ta indikace platí, pokud to zdroj rozlišuje "
        "(\"dospělí\", \"děti od 1 roku\", \"děti od 4 let a dospívající\"). "
        "Když zdroj skupiny nerozlišuje, klíč vynech.\n"
        "\nPříklad: {\"indikace\": [{\"doslovne\": \"astma bronchiale I. typu\", "
        "\"laicky\": \"alergické astma\"}, "
        "{\"doslovne\": \"Léčba refluxní ezofagitidy\", "
        "\"laicky\": \"léčba zánětu jícnu\", \"skupina\": \"děti od 1 roku\"}]}"
    ),
    "kontraindikace": (
        "Z textu sekce kontraindikace vytvoř JSON: {\"kontraindikace\": [{...}]}. "
        "Každý objekt má klíče: doslovne, laicky.\n"
        "- doslovne: JEDEN případ, kdy se lék nesmí užívat, opsaný ze zdroje "
        "DOSLOVA. Nezjednodušuj – slouží k ověření proti dokumentu.\n"
        "- laicky: TENTÝŽ případ řečený laicky (hypersenzitivita → alergie). "
        "Když je srozumitelný i laikovi, zopakuj ho.\n"
        "\nPOZOR na věkové hranice a smysl vztahu – 'děti do 2 let' znamená "
        "MLADŠÍ než 2 roky, ne starší. Opiš to přesně.\n"
        "\nKAŽDÝ případ uveď zvlášť, NESLUČUJ je do jedné položky.\n"
        "\nPříklad: {\"kontraindikace\": [{\"doslovne\": \"hypersenzitivita na "
        "léčivou látku\", \"laicky\": \"alergie na složky léku\"}]}"
    ),
    "davkovani": (
        "Z textu sekce dávkování vytvoř JSON: {\"davkovani\": [{...}]}. "
        "Každý objekt má klíče: pacient, davka, frekvence, poznamka. "
        "Vytvoř samostatnou položku pro každou skupinu pacientů. "
        "Příklad: {\"davkovani\": [{\"pacient\": \"dospělí\", \"davka\": \"500 mg\", "
        "\"frekvence\": \"3–4x denně\", \"poznamka\": \"max 4 g/den\"}]}"
    ),
    "nezadouci_ucinky": (
        "Z textu sekce nežádoucí účinky vytvoř JSON: {\"nezadouci_ucinky\": [{...}]}. "
        "Každý objekt má klíče: ucinek, ucinek_laicky, frekvence, organovy_system.\n"
        "- ucinek: JEDEN nežádoucí účinek opsaný ze zdroje DOSLOVA, včetně "
        "odborného termínu. Nezjednodušuj ho – slouží k ověření proti dokumentu. "
        "Když je ve zdroji na jednom řádku víc účinků oddělených čárkou, "
        "udělej z KAŽDÉHO samostatnou položku.\n"
        "- ucinek_laicky: TENTÝŽ účinek řečený tak, jak by ho popsal laik "
        "(trombocytopenie → nízký počet krevních destiček, nauzea → nevolnost, "
        "angioedém → otok kůže a sliznic, pyróza → pálení žáhy). "
        "Bez latiny a bez odborných slov. Když je termín srozumitelný "
        "i laikovi (např. \"únava\"), zopakuj ho beze změny.\n"
        "Vynechej hvězdičky a odkazy na poznámky pod čarou (\"kopřivka *\" -> \"kopřivka\"). "
        "Účinek musí být POJEM, ne věta – když je ve zdroji celá věta (\"Velmi vzácně byly hlášeny závažné kožní reakce\"), vytáhni z ní jen ten účinek.\n"
        "- frekvence: přesně jedna z hodnot: velmi časté, časté, méně časté, "
        "vzácné, velmi vzácné, není známo\n"
        "- organovy_system: název orgánového systému ze zdroje, opiš ho DOSLOVA "
        "(např. \"Poruchy kůže a podkožní tkáně\"). Když u položky žádný není, dej null.\n"
        "\nProjdi text CELÝ až do konce a zpracuj KAŽDOU skupinu, i tu poslední "
        "a i tu, která se nejmenuje jako orgán (např. \"Vyšetření\"). "
        "Když je nějaká skupina frekvence ve zdroji prázdná, nic si nedoplňuj.\n"
        + POPIS_FORMATU +
        "\nPříklad: {\"nezadouci_ucinky\": [{\"ucinek\": \"urtikarie\", "
        "\"ucinek_laicky\": \"kopřivka\", "
        "\"frekvence\": \"vzácné\", \"organovy_system\": \"Poruchy kůže a podkožní tkáně\"}]}"
    ),
}

# Sekce, ktere maji dvojici odborny termin + laicky tvar, a tedy podlehaji
# ciselniku pojmu. Davkovani tu NENI - to jsou cisla, ne terminy.
SEKCE_S_LAICKYM_TVAREM = {"nezadouci_ucinky", "indikace", "kontraindikace"}

# Povinné klíče položek – kontrola, že model dodržel schéma.
POVINNE_KLICE = {
    "davkovani": {"pacient", "davka"},
    "nezadouci_ucinky": {"ucinek", "ucinek_laicky", "frekvence"},
    "indikace": {"doslovne", "laicky"},
    "kontraindikace": {"doslovne", "laicky"},
}


@dataclass
class VysledekExtrakce:
    sekce: str
    polozky: list = field(default_factory=list)
    stav: str = "ok"          # viz tabulka extrakce_stav v zadani.md
    duvod: str = ""
    model: str = ""
    cas_s: float = 0.0
    surova_odpoved: str = ""


def normalizuj_frekvenci(hodnota: str | None) -> tuple[str | None, int]:
    """Text frekvence -> (kanonický text, rank).

    LLM vrací varianty ("Velmi časté", "caste (>=1/100)"), proto se před
    mapováním odstraní diakritika, závorky a přebytečné mezery.
    Neznámá hodnota dostane rank 9, ne NULL – ať řazení funguje konzistentně.
    """
    import re
    import unicodedata

    if not hodnota:
        return None, FREKVENCE_RANK_NEZNAMA

    t = re.sub(r"\(.*?\)", " ", str(hodnota))          # pryč "(≥1/100 až <1/10)"
    t = "".join(z for z in unicodedata.normalize("NFKD", t) if not unicodedata.combining(z))
    t = re.sub(r"\s+", " ", t).strip().lower().rstrip(":")

    if t in FREKVENCE_SYNONYMA:
        t = FREKVENCE_SYNONYMA[t]

    if t in FREKVENCE_RANK:
        return _KANON_FREKVENCE[FREKVENCE_RANK[t]], FREKVENCE_RANK[t]

    # Překlep. Model napsal "neste známo" (9x) místo "není známo" – hodnota
    # mimo číselník je u frekvence vážná věc, protože se podle ní filtruje
    # i řadí. Připojíme ji na nejbližší platnou hodnotu.
    from difflib import get_close_matches

    blizke = get_close_matches(t, FREKVENCE_RANK.keys(), n=1, cutoff=0.75)
    if blizke:
        return _KANON_FREKVENCE[FREKVENCE_RANK[blizke[0]]], FREKVENCE_RANK[blizke[0]]

    return str(hodnota).strip(), FREKVENCE_RANK_NEZNAMA


# Kanonický text frekvence podle ranku z číselníku.
_KANON_FREKVENCE = {1: "velmi časté", 2: "časté", 3: "méně časté",
                    4: "vzácné", 5: "velmi vzácné", 9: "není známo"}

# Jiná formulace téhož, kterou přiblížná shoda nechytí ("neznámá frekvence"
# proti "není známo" je jiný řetězec, ne překlep).
FREKVENCE_SYNONYMA = {
    "neznama frekvence": "neni znamo",
    "frekvence neznama": "neni znamo",
    "neni znama": "neni znamo",
    "neni znamá": "neni znamo",
    # Starsi ceska SPC pouzivaji vyrazy MIMO ciselnik EU. Mapuji se na
    # "neni znamo" ZAMERNE: "ojedinele" nema v EU kategoriich presny
    # protejsek a dosadit odhadem "vzacne" by znamenalo tvrdit frekvenci,
    # kterou dokument neuvadi. U zdravotniho udaje je priznat neznalost
    # lepsi nez hadat. Priklad: ALGESAL, "Ojedinele kontaktni alergie".
    "ojedinele": "neni znamo",
    "vyjimecne": "neni znamo",
    "zridka": "neni znamo",
    "v ojedinelych pripadech": "neni znamo",
}


def normalizuj_skupinu(hodnota: str | None) -> tuple[str, str]:
    """Skupina pacientů -> (text pro zobrazení, kód pro filtr).

    Nikdy nevrací prázdno. Když zdroj skupinu nerozlišuje, vrátí explicitní
    'není uvedeno' / 'neuvedeno' – ze scházející hodnoty by nešlo poznat,
    jestli ji zdroj neuvádí, nebo ji model přehlédl. Stejný princip jako
    u stavů extrakce (viz stavy.md).

    Text zůstává DOSLOVA ze zdroje ("děti od 1 roku a s hmotností ≥ 10 kg"),
    protože ta podmínka je zdravotně podstatná. Kód je hrubší, aby se dalo
    filtrovat – detail by jako filtr nefungoval, každý lék ho píše jinak.
    """
    import unicodedata

    from common.config import SKUPINA_NEUVEDENO, SKUPINA_TEXT_NEUVEDENO

    text = (hodnota or "").strip()
    if not text:
        return SKUPINA_TEXT_NEUVEDENO, SKUPINA_NEUVEDENO

    bez = "".join(z for z in unicodedata.normalize("NFKD", text.lower())
                  if not unicodedata.combining(z))

    # Pořadí je podstatné: "děti a dospívající" má padnout na 'deti',
    # protože dětská skupina je ta omezující.
    for jehla, kod in (("kojen", "kojenci"), ("novorozen", "kojenci"),
                       ("det", "deti"), ("dit", "deti"),
                       ("dospivaj", "dospivajici"),
                       ("dospel", "dospeli"),
                       ("starsi", "starsi"), ("senior", "starsi")):
        if jehla in bez:
            return text, kod
    return text, "jine"


_OHRADKA = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _ocisti_odpoved(s: str) -> str:
    """Sundá markdownovou ohrádku kolem JSONu.

    qwen3.5:122b občas vrátí ```json {...} ``` i při zapnutém JSON módu
    (`format: json`). Data jsou přitom v pořádku – bez tohohle ošetření
    spadne celá sekce na "nevalidní JSON: line 1 column 1".
    """
    t = s.strip()
    if t.startswith("```"):
        t = _OHRADKA.sub("", t).strip()
    return t


# Práh podobnosti pro opravu překlepu v názvu klíče. Změřeno na skutečných
# i vymyšlených případech: reálné překlepy sedí na 0,77-0,97, nesouvisející
# slova nejvýš na 0,57 ("ucinnost" vs "ucinek" = 0,571), a druhý nejlepší
# kandidát je vždy pod 0,54. Práh 0,7 to rozdělí čistě.
# POZOR: 0,8 je moc přísné – "ucinker" má proti "ucinek" jen 0,769.
_PRAH_PODOBNOSTI_KLICE = 0.7


def _oprav_klice(polozka: dict, ocekavane: set[str]) -> dict:
    """Opraví překlepy v názvech klíčů.

    Model napsal "ucinker" místo "ucinek" a shodilo to 6 z 18 položek
    a s nimi celou sekci. Klíč, který se od očekávaného liší o pár znaků,
    se přemapuje; neznámé klíče se nechají být.
    """
    from difflib import get_close_matches

    opravena: dict = {}
    for k, v in polozka.items():
        if k in ocekavane:
            opravena[k] = v
            continue
        zbyvajici = ocekavane - set(opravena)
        blizke = get_close_matches(k, zbyvajici, n=1, cutoff=_PRAH_PODOBNOSTI_KLICE)
        opravena[blizke[0] if blizke else k] = v
    return opravena


def extrahuj_sekci(
    nazev_sekce: str,
    text: str,
    *,
    model: str = MODEL_EXTRAKCE,
    base_url: str | None = None,
    orezat: bool = True,
    pokusy: int = 2,
) -> VysledekExtrakce:
    """Převede text jedné sekce na strukturované položky.

    orezat=True zkrátí vstup na jádro (viz sekce.orizni_na_jadro). Ořez se
    dělá až tady, ne při ukládání sekcí – na disku zůstává úplný text,
    protože slouží i ke kontrole proti PDF.

    pokusy>1 zopakuje volání, když model vrátí prázdno nebo nepoužitelnou
    odpověď. Výpadky jsou nahodilé (AERIUS vrátil prázdné pole nad textem,
    ve kterém dvě indikace jasně jsou), takže opakování je levnější
    než ruční dohledávání.
    """
    from common.sekce import orizni_na_jadro

    if nazev_sekce not in PROMPTY:
        raise ValueError(f"neznámá sekce: {nazev_sekce}")

    if not text or len(text.strip()) < 20:
        return VysledekExtrakce(nazev_sekce, [], "prazdna", "text sekce je prázdný/kratičký")

    if orezat:
        text = orizni_na_jadro(text, nazev_sekce)

    v = _jeden_pokus(nazev_sekce, text, model=model, base_url=base_url)
    for pokus in range(2, pokusy + 1):
        if v.polozky and v.stav in ("neovereno", "castecna"):
            break
        v = _jeden_pokus(nazev_sekce, text, model=model, base_url=base_url)
        if v.polozky and v.stav in ("neovereno", "castecna"):
            v.duvod = (v.duvod + f" (uspělo až na {pokus}. pokus)").strip()
            break
    return v


def _jeden_pokus(
    nazev_sekce: str,
    text: str,
    *,
    model: str,
    base_url: str | None,
) -> VysledekExtrakce:
    import time

    prompt = f"{PROMPTY[nazev_sekce]}\n\n--- TEXT SEKCE ---\n{text}\n--- KONEC ---"

    t0 = time.perf_counter()
    try:
        odpoved = chat(
            prompt,
            system=SYSTEM_PROMPT,
            model=model,
            base_url=base_url,
            json_mode=True,
        )
    except Exception as e:
        return VysledekExtrakce(
            nazev_sekce, [], "selhala_extrakce",
            f"{type(e).__name__}: {e}", model, time.perf_counter() - t0,
        )
    cas = time.perf_counter() - t0

    try:
        data = json.loads(_ocisti_odpoved(odpoved))
    except json.JSONDecodeError as e:
        return VysledekExtrakce(
            nazev_sekce, [], "selhala_extrakce",
            f"nevalidní JSON: {e}", model, cas, odpoved[:400],
        )

    polozky = data.get(nazev_sekce) if isinstance(data, dict) else data
    if polozky is None and isinstance(data, dict) and len(data) == 1:
        polozky = next(iter(data.values()))      # model použil jiný název klíče
    if not isinstance(polozky, list):
        return VysledekExtrakce(
            nazev_sekce, [], "selhala_extrakce",
            f"očekáváno pole, přišlo {type(polozky).__name__}", model, cas, odpoved[:400],
        )
    if not polozky:
        return VysledekExtrakce(nazev_sekce, [], "prazdna", "model vrátil prázdné pole", model, cas)

    # Kontrola povinných klíčů u objektových sekcí
    stav, duvod = "neovereno", ""
    povinne = POVINNE_KLICE.get(nazev_sekce)
    if povinne:
        vsechny_klice = povinne | {"organovy_system", "frekvence", "poznamka",
                                   "ucinek", "ucinek_laicky", "doslovne", "laicky",
                                   "skupina", "skupina_kod"}
        polozky = [_oprav_klice(p, vsechny_klice) if isinstance(p, dict) else p
                   for p in polozky]
        dobre = [p for p in polozky if isinstance(p, dict) and povinne <= p.keys()]
        if not dobre:
            return VysledekExtrakce(
                nazev_sekce, [], "selhala_extrakce",
                f"žádná z {len(polozky)} položek nemá klíče {sorted(povinne)}",
                model, cas, odpoved[:400],
            )
        if len(dobre) < len(polozky):
            # Část dat se zachránit dá – zahodit kvůli tomu celou sekci by
            # bylo horší. Stav to ale musí přiznat, ne se tvářit jako v pořádku.
            stav = "castecna"
            duvod = (f"{len(polozky) - len(dobre)} z {len(polozky)} položek "
                     f"zahozeno, chybí klíče {sorted(povinne)}")
        polozky = dobre

    # Skupina pacientu se dopoclni VZDY, i kdyz ji model neuvedl - viz
    # normalizuj_skupinu(). Deterministicke, zadny model u toho neni.
    if nazev_sekce == "indikace":
        for p in polozky:
            if isinstance(p, dict):
                text, kod = normalizuj_skupinu(p.get("skupina"))
                p["skupina"] = text
                p["skupina_kod"] = kod

    # Sjednoceni na rizene slovniky. Vsechno nize je DETERMINISTICKE -
    # zadny dalsi model, jen ciselniky. Pousti se pri kazde extrakci, takze
    # data jsou konzistentni uz na vystupu, ne az po ocisteni.
    if nazev_sekce == "nezadouci_ucinky":
        from common.meddra import normalizuj_soc

        for p in polozky:
            kanon, rank = normalizuj_frekvenci(p.get("frekvence"))
            p["frekvence"] = kanon
            p["frekvence_rank"] = rank
            soc, jak = normalizuj_soc(p.get("organovy_system"))
            p["organovy_system"] = soc
            if jak == "pribuzna":
                p["organovy_system_opraveno"] = True

    # Slovnik pojmu je AUTORITA pro laicky tvar. Kdyz termin zna, to co
    # vygeneroval model se zahodi - jinak by kazdy beh prepsal rucni
    # opravy cloveka a termin by mel u kazdeho leku jinou podobu.
    #
    # POZOR: plati pro VSECHNY sekce s laickym tvarem, ne jen pro nezadouci
    # ucinky. Do 24.8. to bylo jen tady a indikace s kontraindikacemi
    # zustavaly bez dozoru - odhalilo se to na termine "neuralgie", ktery
    # mel pri kazdem behu jinou podobu.
    if nazev_sekce in SEKCE_S_LAICKYM_TVAREM:
        from common.slovnik import uplatni

        ze_slovniku, od_modelu = uplatni(polozky)
        if ze_slovniku:
            duvod = (duvod + f" (laicky tvar: {ze_slovniku} ze slovniku, "
                             f"{od_modelu} od modelu)").strip()

    return VysledekExtrakce(nazev_sekce, polozky, stav, duvod, model, cas)
