"""Od kolika let se smi lek pouzit - odvozeno z SPC BEZ MODELU.

PROC: filtr „lek na reflux pro deti". Indikace (4.1) vek casto neuvadi,
ale davkovani (4.2) ma povinnou podsekci „Pediatricka populace" a
kontraindikace (4.3) zakazy typu „deti mladsi 2 let". Vsechny tri sekce
uz jsou vyextrahovane, takze vek se da spocitat deterministicky.

ZASADA: v pochybnostech OMEZIT. Pro laika je horsi doporucit diteti lek,
ktery pro nej neni, nez ho neukazat. Proto:
  - davka „nestanovena / nedoporucuje se / nesmi" = pro tu skupinu NE
  - kontraindikace s vekem = tvrdy zakaz, i kdyz je podminena
    („deti do 16 let pri horecnatem onemocneni" - aspirin, Reyeuv syndrom)
  - vek, ktery z textu nejde urcit = „nevim" (NULL), ne „ano"

POZOR na cestinu:
  „kojeni" (4.3) = zakaz pri KOJENI MATKY, ne pro kojence -> ignorovat
  „nesmi" v poznamce („max. davka nesmi byt prekrocena") neni zakaz -
    zakaz se posuzuje podle pole `davka`, ne podle poznamky
"""

import re

# Vekove hranice v letech. Horni mez je VYLUCNA (do 18 = mladsi nez 18).
DOSPELY = 18.0
# Filtr „pro dospělé" (hledani.py): lek musi mit spodni hranici veku aspon
# tady. 12 = bezna hranice „dospělí a dospívající od 12 let" (IBALGIN,
# BRUFEN); s 18 by zbyly hlavne leky na predpis a nemocnicni, s 15 by
# vypadl i IBALGIN. Rozhodnuti 6. 10. 2026, cisla ve docs/hledani_vek.md 2b.
DOSPELI_VEK_OD = 12.0
STARSI = 65.0

_C = r"(\d+(?:[,.]\d+)?)"                    # cislo, i desetinne s carkou
_JEDN = r"(let|roku|roky|rok|měsíc\w*|měs\.?|týdn\w*|týden)"


def _roky(cislo: str, jednotka: str) -> float:
    x = float(cislo.replace(",", "."))
    j = jednotka.lower()
    if j.startswith("měs"):
        return x / 12
    if j.startswith("týd"):
        return x / 52
    return x


# Poradi je podstatne - rozsah pred jednostrannou hranici.
_ROZSAH = re.compile(rf"(?:od\s+)?{_C}\s*(?:–|-|až|do)\s*{_C}\s*{_JEDN}", re.I)
_OD = re.compile(
    rf"(?:od|nad|≥|>=|starší\s+(?:než\s+)?|ve\s+věku)\s*{_C}\s*{_JEDN}"
    rf"|{_C}\s*{_JEDN}\s*(?:a\s+starší|a\s+více|a\s+výše|a\s+starších)", re.I)
_DO = re.compile(
    rf"(?:do|pod|<|mladší\s+než|mladší|méně\s+než|mladších\s+než|mladších)\s*{_C}\s*{_JEDN}", re.I)

# Slovni skupiny, kdyz cislo chybi. Sirsi pojem = sirsi rozsah.
_SLOVA = [
    (re.compile(r"novoroz", re.I), (0.0, 0.1)),
    (re.compile(r"kojen(?!í)(c|ců|ce|cům|ci)", re.I), (0.0, 1.0)),   # NE „kojení"
    (re.compile(r"batol", re.I), (1.0, 3.0)),
    (re.compile(r"pediatr|dět|děti|dítě|dítět", re.I), (0.0, DOSPELY)),
    (re.compile(r"dospívaj", re.I), (12.0, DOSPELY)),
    (re.compile(r"star(ší|ších)\s+(pacient|osob|lid|dospěl)|senio|geriatr", re.I), (STARSI, None)),
    (re.compile(r"dospěl", re.I), (DOSPELY, None)),
]


# Obecne „deti / pediatricka populace" bez cisla NEURCUJE spodni hranici
# („deti s vrozenym glaukomem", „deti po transplantaci"). Rika jen „pro deti
# ano". 512 z 976 SPC vychazelo „od narozeni" jen kvuli tomuhle slovu.
_OBECNE_DETI = re.compile(r"pediatr|dět|děti|dítě|dítět", re.I)


def je_detska(text: str | None) -> bool:
    """Tyka se skupina deti (jakkoli)? Pro priznak pro_deti."""
    v = vek_z_textu(text)
    return v is not None and v[0] < DOSPELY


def vek_urcity(text: str | None) -> tuple[float, float | None] | None:
    """Jako vek_z_textu, ale jen z URCITEHO udaje: cislo nebo slovo s jasnou
    hranici (novorozenci, kojenci, dospivajici, dospeli, starsi). Samotne
    „deti" vrati None."""
    t = str(text or "")
    if ma_vyslovny_vek(t):
        # Jen HORNI hranice („deti do 6 let: 13–16 kg") spodni neurcuje -
        # PARALEN 125 MG a IBALGIN BABY z toho vychazely „od 0 let".
        # U ZAKAZU je „do X" spravne od 0, tady jde o kladny dukaz.
        if not (_ROZSAH.search(t) or _OD.search(t)):
            return None
        return vek_z_textu(t)
    bez = _OBECNE_DETI.sub(" ", t)
    return vek_z_textu(bez)


def vek_z_textu(text: str | None) -> tuple[float, float | None] | None:
    """Vekovy rozsah (od, do) v letech z popisu skupiny, nebo None.

    'děti ve věku 1–6 let' -> (1, 6); 'dospělí a dospívající od 12 let'
    -> (12, None); 'děti mladší 2 let' -> (0, 2); 'starší pacienti' ->
    (65, None). Bez veku ('pacienti s poruchou ledvin') -> None.
    """
    if not text:
        return None
    t = str(text)
    m = _ROZSAH.search(t)
    if m:
        return _roky(m.group(1), m.group(3)), _roky(m.group(2), m.group(3))
    od = _OD.search(t)
    do = _DO.search(t)
    if od or do:
        lo = _roky(*[g for g in od.groups() if g][:2]) if od else None
        hi = _roky(*[g for g in do.groups() if g][:2]) if do else None
        if lo is None:
            lo = 0.0
        return lo, hi
    rozsahy = [r for vzor, r in _SLOVA if vzor.search(t)]
    if not rozsahy:
        return None
    lo = min(r[0] for r in rozsahy)
    hi = None if any(r[1] is None for r in rozsahy) else max(r[1] for r in rozsahy)
    return lo, hi


# Davka, ktera rika „pro tuhle skupinu ne".
_ZAKAZ = re.compile(
    r"nestanoven|nebyl[aoy]?\s+stanoven|nedoporuč|nelze\s+doporučit|nemá\s+(se|být)\s+"
    r"(používat|podávat|užívat|podáván|používán)|nesmí|kontraindik|nepoužív|"
    r"není\s+(určen|indikován|doporučen)|nejsou\s+(k\s+dispozici|dostupné)|"
    r"neexist|nebyl[aoy]?\s+(hodnocen|prokázán|studován)|bez\s+údajů|"
    r"pouze\s+(na\s+doporučení|po\s+poradě|pod\s+dohledem)\s+lékaře", re.I)


def je_zakaz(davka: str | None) -> bool:
    """Rika davka, ze pro tuto skupinu se lek nepouziva? (ne poznamka!)"""
    return bool(davka) and bool(_ZAKAZ.search(str(davka)))


# Kladny dukaz = KONKRETNI davka. „neuvedeno" / „-" neni davka: GAVISCON
# „deti mladsi 12 let: davka neuvedeno, pouze na doporuceni lekare" by jinak
# vysel jako „od 0 let".
_MA_DAVKU = re.compile(r"\d|\b(jedn|dvě|dva|tři|čtyři|pět|půl|polovin)", re.I)


def ma_vyslovny_vek(text: str | None) -> bool:
    """Obsahuje text vek v CISLECH? Slovo „deti" samo nestaci - „deti s
    hmotnosti pod 20 kg" (PARALEN 4.3) neni zakaz do 18 let."""
    t = str(text or "")
    return bool(_ROZSAH.search(t) or _OD.search(t) or _DO.search(t))


# Dite smi lek JEN na pokyn lekare = pro laika NE. ASPIRIN 500 MG ma pro
# deti davku 60 mg/kg, ale „nemaji uzivat kyselinu acetylsalicylovou bez
# lekarskeho predpisu" (Reyeuv syndrom je az v 4.4, ktery neextrahujeme).
# POZOR: „Bez pokynu lekare nejdele 3 dny" (delka lecby dospelych) zakaz NENI.
_JEN_S_LEKAREM = re.compile(
    r"(nemají|nesmí|nemá)\s+\w*\s*(užívat|používat|podávat)[^.]{0,60}bez\s+(lékařsk|porady|předpisu|doporučení)"
    r"|(jen|pouze)\s+(na|po|pod|podle)\s+(doporučení|poradě|předpis|dohledem|pokynu)\s+\w*\s*lékař"
    r"|jen\s+na\s+lékařský\s+předpis|pouze\s+na\s+lékařský\s+předpis", re.I)


def druh_polozky(p: dict) -> str:
    """'ano' (konkretni davka), 'ne' (zakaz) nebo '' (nejde rict)."""
    davka, pozn = p.get("davka"), p.get("poznamka")
    if je_zakaz(davka):
        return "ne"
    if pozn and _JEN_S_LEKAREM.search(str(pozn)):
        return "ne"
    if davka and _MA_DAVKU.search(str(davka)):
        return "ano"
    if je_zakaz(pozn):          # davka bez cisla + „pouze na doporuceni lekare"
        return "ne"
    return ""


# --- Vek v DOTAZU uzivatele ------------------------------------------------
# Deterministicky, ne pres router: router je nedeterministicky (obcas ztrati
# nazev leciva) a tohle je filtr s dopadem na bezpecnost - nesmi se ztratit.

_CISLOVKY = {"jedno": 1, "dvou": 2, "tří": 3, "čtyř": 4, "pěti": 5, "šesti": 6,
             "sedmi": 7, "osmi": 8, "devíti": 9, "deseti": 10, "jedenácti": 11,
             "dvanácti": 12, "třinácti": 13, "čtrnácti": 14, "patnácti": 15}
_DETSKY = re.compile(r"\b((?:u|pro)\s+(?:dítě\w*|dět\w*)|dětem|dítě\w*|děti|dětsk\w*|"
                     r"pediatr\w*|školák\w*|předškolák\w*)\b", re.I)
_KOJENEC = re.compile(r"\b(kojen(?!í)\w*|miminek|miminko|miminka|novoroz\w*)\b", re.I)
_BATOLE = re.compile(r"\bbatol\w*", re.I)
_VEK_CISLO = re.compile(r"(\d+)\s*[- ]?\s*(let[ýáéiou]\w*|let|roky|roků|rok\w*|měsíc\w*|měsíčn\w*)", re.I)
_VEK_SLOVO = re.compile(r"\b(" + "|".join(_CISLOVKY) + r")(let[ýáéiou]\w*|měsíčn\w*)", re.I)

# Samostatna cislovka + jednotka: „dite sest let", „tri roky", „pet mesicu".
# 1. 10. 2026: „horecka dite sest let" vek NEZACHYTILO (znal jsem jen kmeny
# „sesti-lete") -> filtr jen pro_deti a na 1. miste BRUFEN od 12 let.
_ZAKLADNI = {"jeden": 1, "jedna": 1, "jedno": 1, "dva": 2, "dvě": 2, "tři": 3,
             "čtyři": 4, "pět": 5, "šest": 6, "sedm": 7, "osm": 8, "devět": 9,
             "deset": 10, "jedenáct": 11, "dvanáct": 12, "třináct": 13,
             "čtrnáct": 14, "patnáct": 15, "šestnáct": 16, "sedmnáct": 17}
_CISLOVKY.update({"šestnácti": 16, "sedmnácti": 17})
_VEK_SLOVO = re.compile(r"\b(" + "|".join(_CISLOVKY) + r")(let[ýáéiou]\w*|měsíčn\w*)", re.I)
_VEK_ZAKLADNI = re.compile(
    r"\b(" + "|".join(sorted(_ZAKLADNI, key=len, reverse=True)) + r")\s+"
    r"(let|roky|roků|rok\w*|měsíc\w*|měsíců|týdn\w*|týden)\b", re.I)
_PUL_ROKU = re.compile(r"\bpůl\s*roku\b|\bpůlroční\w*", re.I)


def vek_z_dotazu(dotaz: str) -> tuple[bool | None, float | None]:
    """(pro_deti, vek pacienta v letech) z dotazu laika.

    'lék na reflux pro děti'      -> (True, None)
    'kašel u tříletého dítěte'    -> (True, 3)
    'horečka dítě 5 let'          -> (True, 5)
    'něco na rýmu pro miminko'    -> (True, 0.5)
    'bolí mě hlava'               -> (None, None)
    """
    t = dotaz or ""
    vek = None
    m = _VEK_CISLO.search(t)
    if m:
        x = float(m.group(1))
        vek = x / 12 if m.group(2).lower().startswith("měs") else x
    else:
        m = _VEK_SLOVO.search(t)
        if m:
            x = float(_CISLOVKY[m.group(1).lower()])
            vek = x / 12 if m.group(2).lower().startswith("měs") else x
        else:
            m = _VEK_ZAKLADNI.search(t)
            if m:
                x = float(_ZAKLADNI[m.group(1).lower()])
                j = m.group(2).lower()
                vek = x / 12 if j.startswith("měs") else (x / 52 if j.startswith("týd") else x)
            elif _PUL_ROKU.search(t):
                vek = 0.5
    if _KOJENEC.search(t) and vek is None:
        vek = 0.5
    elif _BATOLE.search(t) and vek is None:
        vek = 2.0
    detsky = bool(_DETSKY.search(t) or _KOJENEC.search(t) or _BATOLE.search(t))
    if vek is not None and vek >= DOSPELY:
        return None, None               # "pro 40 let" neni detsky dotaz
    if vek is not None and not detsky and not _VEK_SLOVO.search(t):
        # cislo bez zminky o diteti ("bolest 3 roky") - nebrat jako vek
        return None, None
    return (True if detsky or vek is not None else None), vek


# „pro dospělé", „u dospělých", „dospělý" - i bez diakritiky. Zadost
# o lek PRO DOSPELE: z vysledku vypadnou detske pripravky (jen_deti).
_DOSPELY_DOTAZ = re.compile(r"\b(?:(?:pro|u)\s+)?dosp[ěe]l\w*", re.I)


def dospeli_z_dotazu(dotaz: str) -> bool:
    """Chce uzivatel lek PRO DOSPELE? ('něco na kocovinu pro dospělé')

    Kdyz dotaz zminuje i dite ('pro děti i dospělé'), nefiltruje se nic -
    obe skupiny naraz nejdou splnit a detsky filtr ma prednost (bezpecnost).
    """
    t = dotaz or ""
    if not _DOSPELY_DOTAZ.search(t):
        return False
    return vek_z_dotazu(t)[0] is None


def bez_veku(text: str) -> str:
    """Text dotazu bez zminky o diteti/veku - pro vektor. Vek resi filtr,
    ve vektoru by jen redil vyznam (CLAUDE.md: kazde slovo navic stoji)."""
    t = text or ""
    for vzor in (_VEK_CISLO, _VEK_SLOVO, _VEK_ZAKLADNI, _PUL_ROKU, _DETSKY, _KOJENEC, _BATOLE,
                 _DOSPELY_DOTAZ):
        t = vzor.sub(" ", t)
    t = re.sub(r"\b(pro|u|pro\s+moje|pro\s+naše|mého|našeho|malé\w*)\s*$", " ", t.strip(), flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


# Stitky podminek u skupiny pacientu v davkovani.
PODMINKY = {
    "ledviny": re.compile(r"ledvin|renál|clearance|CrCl|GFR|eGFR|dialýz", re.I),
    "jatra": re.compile(r"jater|jaterní|hepat|Child", re.I),
    "dialyza": re.compile(r"dialýz", re.I),
    "hmotnost": re.compile(r"\bkg\b|hmotnost", re.I),
    "interakce": re.compile(r"CYP|inhibitor|induktor|současně|v kombinaci|souběžn", re.I),
    "tehotenstvi": re.compile(r"těhotn|kojící", re.I),
}


def podminky(text: str | None) -> list[str]:
    t = str(text or "")
    return [k for k, vzor in PODMINKY.items() if vzor.search(t)]


# Jedno SPC casto popisuje vic forem (NOVALGIN: tablety i injekce). Davkovani
# pro deti je tam jen u injekci - u tablet by jinak vyslo „od 0 let".
# Rodina formy: (slova v textu SPC, kod lekove formy SUKL). VIBROCIL ma jedno
# SPC pro kapky i sprej a „nosni sprej neni urcen detem do 6 let" nesmi
# posunout kapky (od 1 roku).
_RODINY = {
    "injekce": (r"injek|infuz|intraven|i\.\s?v\.|intramusk|i\.\s?m\.|parenter", r"INJ|INF|IVN|IMS"),
    "sprej":   (r"sprej|spray|rozprašov|vstřik", r"SPR"),
    "kapky":   (r"kapk", r"GTT"),
    "cipky":   (r"čípk|rektál|supp", r"SUP"),
    "tablety": (r"tablet", r"TBL|TAB"),
    "tobolky": (r"tobol|kapsl", r"CPS"),
    "tekute":  (r"sirup|suspenz|perorální\s+roztok|kapalin", r"SIR|SUS|POR SOL|SOL POR"),
    "granule": (r"granul|prášek|sáček|sáčk", r"GRA|PLV|POR PLV"),
    "kozni":   (r"krém|mast|gel\b|na\s+kůži", r"CRM|UNG|GEL|DRM"),
}
_RODINY_RE = {k: (re.compile(t, re.I), re.compile(rf"\b(?:{f})", re.I))
              for k, (t, f) in _RODINY.items()}


def _jina_forma(text: str | None, forma: str | None) -> bool:
    """Tyka se polozka VYSLOVNE jine lekove formy nez ma lek?

    Ano, kdyz text jmenuje nejakou formu, lek ma znamou formu a ta mezi
    jmenovanymi neni. Text bez zminky o forme = plati pro vse.
    """
    if not forma or not text:
        return False
    moje = {k for k, (_, f) in _RODINY_RE.items() if f.search(forma)}
    zminene = {k for k, (t, _) in _RODINY_RE.items() if t.search(str(text))}
    return bool(moje and zminene and not (moje & zminene))


# --- Detsky pripravek (filtr „pro dospělé") --------------------------------
# Lek urceny JEN detem: NUROFEN PRO DĚTI, PANADOL BABY, KLACID sirup 125 mg.
# Dospely, ktery hleda „něco na bolest hlavy pro dospělé", je nechce.
#
# POZOR, proc to NENI „vek_od >= 18": to by vyhodilo polovinu trhu vcetne
# NUROFENU 200 MG a IBALGINU (oba od 12 let) a dospelemu by zbyly jen leky
# vyhradne pro dospele. Vyhazuje se jen to, co je JEN pro deti.
_DETSKY_NAZEV = re.compile(
    r"\bPRO\s+DĚTI\b|\bJUNIOR\b|\bBABY\b|\bDĚTSK|\bPRO\s+KOJENCE\b|\bPRO\s+INFANTIBUS\b|"
    r"\bKIDS\b|\bPAED\b|\bPAEDIATRIC\b|\bPEDIATRIC\b", re.I)


def je_detsky_pripravek(davkovani: list, forma: str | None = None,
                        nazev: str | None = None) -> tuple[bool, str]:
    """(je lek jen pro deti?, duvod).

    1. NAZEV to rika („PRO DĚTI", „JUNIOR", „BABY") - presne, 30 SPC.
    2. Davkovani (4.2): je aspon jedna davka pro DETI (skupina zacina pod
       12 let a konci do 18) a ZADNA davka pro dospele ani davka bez veku.
       Zmereno 6. 10. 2026 na 5 880 SPC: ~33 SPC navic, spravne ~85 %
       (KLACID sirup, MONTELUKAST 4/5 mg, SANORIN 0,5, PARALEN 100 cipky).
       Znama falesna: FLUTIFORM, VIREAD 245, JODID DRASELNY, infuze
       CHLORID SODNY / GLUKOZA - model u nich dospelou davku neoznacil vekem.

    Co schvalne NEpocita: skupinu „dospívající" samotnou (ELLAONE „ženy vč.
    dospívajících", ACTAIR „dospělí a dospívající 12–17 let") a skupinu
    z indikaci 4.1 (ADVANTAN „děti" u jedne z indikaci).
    """
    if nazev and _DETSKY_NAZEV.search(nazev):
        return True, f"název: {nazev[:40]}"
    detske: list[str] = []
    for p in davkovani or []:
        if not isinstance(p, dict) or druh_polozky(p) != "ano":
            continue
        pac = p.get("pacient")
        if _jina_forma(f"{pac} {p.get('davka') or ''}", forma):
            continue
        v = vek_z_textu(pac)
        if v is None:
            return False, ""                    # davka bez veku = obecna populace
        if v[1] is None or v[1] > DOSPELY or re.search(r"dospěl", str(pac), re.I):
            return False, ""                    # davka saha do dospelosti
        if v[0] < 12:
            detske.append(str(pac)[:60])
    if detske:
        return True, f"4.2 jen dětské dávky: {detske[0]}"
    return False, ""


def vek_spc(davkovani: list, indikace: list, kontraindikace: list,
            forma: str | None = None, nazev: str | None = None) -> dict:
    """Od kolika let lze lek pouzit, s duvodem (pro audit a popisek v GUI).

    Vraci {"vek_od": float|None, "pro_deti": bool|None, "jen_deti": bool,
    "duvody": [str]}. None = z SPC nejde urcit. `forma` = lekova forma
    zastupce (kod SUKL, napr. "TBL NOB", "INJ SOL") - polozky jine formy
    se nepocitaji. `nazev` = nazev leku, jen pro `jen_deti`.
    """
    ven = _vek_spc(davkovani, indikace, kontraindikace, forma)
    jen_deti, duvod = je_detsky_pripravek(davkovani, forma, nazev)
    ven["jen_deti"] = jen_deti
    if jen_deti:
        ven["duvody"] = ven["duvody"] + [f"JEN PRO DĚTI ({duvod})"]
    return ven


def _vek_spc(davkovani: list, indikace: list, kontraindikace: list,
             forma: str | None = None) -> dict:
    duvody: list[str] = []
    kladne: list[float] = []
    zakazy: list[tuple[float, float | None]] = []
    deti_ano = False            # kladne davkovani pro NEJAKOU detskou skupinu

    for p in davkovani or []:
        if not isinstance(p, dict):
            continue
        pac = p.get("pacient")
        # Zakaz s VYSLOVNYM vekem v poznamce jakekoli polozky: NOVALGIN
        # „Tablety se nedoporucuji detem mladsim 15 let" stoji v poznamce
        # u dospelych. Plati jen pro formu, ktere se tyka.
        pozn = p.get("poznamka")
        if pozn and je_zakaz(pozn) and ma_vyslovny_vek(pozn) and not _jina_forma(pozn, forma):
            vz = vek_z_textu(pozn)
            if vz and vz[1] is not None and vz[1] <= DOSPELY:
                zakazy.append((0.0, vz[1]))
                duvody.append(f"4.2 NE do {vz[1]:g} (poznámka): {str(pozn)[:60]}")
        v = vek_z_textu(pac)
        if v is None:
            continue
        if _jina_forma(f"{pac} {p.get('davka') or ''}", forma):
            duvody.append(f"4.2 jiná forma, nepočítá se: {str(pac)[:60]}")
            continue
        druh = druh_polozky(p)
        if druh == "ne":
            zakazy.append(v)
            duvody.append(f"4.2 NE {v}: {str(pac)[:60]}")
        elif druh == "ano":
            deti_ano = deti_ano or v[0] < DOSPELY
            u = vek_urcity(pac)
            if u is not None:
                kladne.append(u[0])
                duvody.append(f"4.2 ANO od {u[0]:g}: {str(pac)[:60]}")
            else:
                duvody.append(f"4.2 ANO děti (věk neuveden): {str(pac)[:60]}")

    for p in indikace or []:
        if not isinstance(p, dict):
            continue
        sk = p.get("skupina")
        v = vek_z_textu(sk)
        if v is None:
            continue
        deti_ano = deti_ano or v[0] < DOSPELY
        u = vek_urcity(sk)
        if u is not None:
            kladne.append(u[0])
            duvody.append(f"4.1 ANO od {u[0]:g}: {str(sk)[:60]}")

    for p in kontraindikace or []:
        if not isinstance(p, dict):
            continue
        txt = str(p.get("doslovne") or "")
        if not ma_vyslovny_vek(txt):
            continue
        v = vek_z_textu(txt)
        # jen zakaz PRO MLADSI ("deti do 2 let"), ne "kojeni", ne dospeli
        if v is not None and v[1] is not None and v[1] <= DOSPELY and v[0] < v[1]:
            zakazy.append((0.0, v[1]))
            duvody.append(f"4.3 NE do {v[1]:g}: {txt[:60]}")

    # Zakaz pro vsechny deti ("deti a dospivajici do 18 let: nestanoveno")
    deti_zakaz = any(lo <= 0 and (hi is None or hi >= DOSPELY) for lo, hi in zakazy)

    if not kladne:
        return {"vek_od": None,
                "pro_deti": (False if deti_zakaz else (True if deti_ano else None)),
                "duvody": duvody or ["vek v SPC neuveden"]}

    vek_od = min(kladne)
    # Zakaz, ktery pokryva spodni hranici, ji posune nahoru (opakovane -
    # 'deti do 2 let NE' a pak 'deti 2-6 let nestanoveno').
    zmena = True
    while zmena:
        zmena = False
        for lo, hi in zakazy:
            if hi is not None and lo <= vek_od < hi:
                vek_od = hi
                zmena = True
            elif hi is None and lo <= vek_od:
                pass    # zakaz „od X nahoru" (starsi) - spodni hranici nemeni
    pro_deti = vek_od < DOSPELY or (deti_ano and not deti_zakaz)
    return {"vek_od": round(vek_od, 2), "pro_deti": pro_deti, "duvody": duvody}
