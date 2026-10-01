"""Hybridni hledani: sémantika (cosine) + cesky fulltext, spojene pres RRF.

Podle zadani je SEMANTIKA to podstatne a fulltext jen doplnek - proto ma
vahu 0,8 ku 0,2, ne pul na pul. Fulltext je tam kvuli dotazum jako
"Paralen 500mg", kde uzivatel pise presny nazev a silu; ty vektor
nepozna spolehlive, protoze "500MG" je jeden token bez vyznamu.

RRF (Reciprocal Rank Fusion) spojuje dve poradi, ne dve skore:

    skore = vaha_sem * 1/(k + poradi_sem) + vaha_fts * 1/(k + poradi_fts)

Duvod, proc poradi a ne skore: cosine similarity a ts_rank maji uplne
jine rozsahy a nijak se nedaji scitat. Poradi je srovnatelne vzdy.
k=60 je akademicky obvykla hodnota; tlumi vliv prvnich mist, aby jedno
poradi nepretlacilo druhe.

FILTRY se aplikuji PRED hledanim (WHERE), ne po nem. Kdyby se filtrovalo
az z vysledku, "volne prodejny lek na bolest" by nejdriv nasel 20 leku
na bolest a pak z nich nechal treba dva - misto aby hledal mezi vsemi
volne prodejnymi.
"""

import logging
from dataclasses import dataclass, field

import psycopg

from common.config import PG_DSN, MODEL_EMBED
from common.dotazy import rozsir

logger = logging.getLogger(__name__)

# Vaha semantiky vs fulltextu. Zadani: "o 500 % je dulezitejsi, aby to
# naslo nejake semanticke veci. Ten fulltext je jen doplnek."
VAHA_SEMANTIKA = 0.8

# Konstanta RRF. 60 je obvykla hodnota z literatury.
RRF_K = 60

# Kolik kandidatu vzit z kazdeho zebricku pred spojenim. Vic nez vysledny
# limit, aby melo RRF co michat.
KANDIDATU = 100


@dataclass
class Filtr:
    """Co se omezuje PRED hledanim. Prazdny filtr = hleda se ve vsem."""
    sekce: list[str] | None = None
    na_predpis: bool | None = None
    hrazeno: bool | None = None
    sila: str | None = None
    atc_prefix: str | None = None
    organovy_system: str | None = None
    # Frekvence se filtruje DVEMA zpusoby a plete se to:
    #   frekvence          PRESNA hodnota - "vzacne" vrati JEN vzacne
    #   frekvence_rank_max "aspon tak caste" - rank <= N
    # Kdyz nekdo chce vzacne a dostane rank_max=4, prijdou i velmi caste
    # a caste, tedy PRESNY OPAK. Zmereno na ABLYMICU: dotaz na vzacne
    # vratil 19 castych a 5 velmi castych. Proto je vychozi PRESNA shoda
    # a rank_max se pouzije jen u formulaci "a castejsi".
    frekvence: str | None = None
    frekvence_rank_max: int | None = None     # 2 = jen caste a castejsi
    skupina_kod: str | None = None
    nazev: str | None = None                  # uzivatel jmenoval konkretni lek
    kod_sukl: str | None = None
    ucinna_latka: str | None = None
    # Vek pacienta (30.9.2026, common/vek.py) - z dotazu deterministicky,
    # v DB leciva.pro_deti / leciva.vek_od odvozene z 4.1 + 4.2 + 4.3.
    # ZASADA: jen leky, kde SPC dite VYSLOVNE pripousti; "nevim" se nezobrazi.
    pro_deti: bool | None = None
    vek: float | None = None
    # Cast nazvu (1. 10. 2026, common/nazev_vzor.py): „lek zacina oxy",
    # „lek obsahuje pox", „lek konci prazol" - JEN v nazvu leku.
    nazev_vzor: object | None = None      # NazevVzor

    def je_prazdny(self) -> bool:
        return all(getattr(self, f.name) is None for f in fields_of(self))

    def je_presny(self) -> bool:
        """Vybral filtr leciva PRESNE, podle rizene hodnoty?

        Nazev, kod SUKL, ucinna latka, sila a ATC jsou hodnoty z API SUKL,
        frekvence je hodnota z ciselniku - bud sedi, nebo ne. Kdyz
        uzivatel jednu z nich uvedl, VYBER UZ PROBEHL a semantika k nemu
        nema co pridat. Prah se proto neuplatnuje.

        Frekvence pribyla 24.8.: dotaz "velmi caste nezadouci ucinky"
        nasel filtrem spravnych 12 radku, ale VSECHNY je odrizl prah -
        dotaz totiz nenese zadny priznak, na kterem by se dala podobnost
        merit. Filtr uz pritom vybral presne to, co clovek chtel.

        Zmereno na dotazu "paracetamol" nad sekci atributy:

            0,611  PARALEN ... PARACETAMOL      spravne
            0,548  ACIFEIN ... PARACETAMOL      spravne
            0,517  ABAKTAL ... PEFLOXACIN       SPATNE
            0,489  OMEPRAZOL ... OMEPRAZOL      SPATNE

        Mezi posledni spravnou a prvni spatnou je rozdil 0,031 a vsechny
        spatne sedi v hustem pasmu tesne pod nimi. Vektor nerozlisi
        paracetamol od pefloxacinu - obojí je pro nej "nazev leciva".
        Prah na cosine by tady jen zahazoval spravne odpovedi: pri 0,55
        by vypadl ACIFEIN, prestoze paracetamol obsahuje.
        """
        if self.nazev_vzor is not None and getattr(self.nazev_vzor, "platny", False):
            return True        # vyber podle pismen nazvu - podobnost nema co merit
        return any([self.nazev, self.kod_sukl, self.ucinna_latka, self.sila,
                    self.atc_prefix, self.frekvence])

    def popis(self) -> str:
        """Filtr lidsky, pro vypis uzivateli - musi byt videt, co se omezilo."""
        casti = []
        if self.sekce:
            casti.append("sekce: " + ", ".join(self.sekce))
        if self.na_predpis is not None:
            casti.append("na předpis" if self.na_predpis else "volně prodejné")
        if self.hrazeno is not None:
            casti.append("hrazené pojišťovnou" if self.hrazeno else "nehrazené")
        if self.sila:
            casti.append(f"síla {self.sila}")
        if self.atc_prefix:
            casti.append(f"ATC {self.atc_prefix}*")
        if self.organovy_system:
            casti.append(f"orgánový systém: {self.organovy_system}")
        if self.frekvence:
            casti.append(f"frekvence: {self.frekvence}")
        if self.frekvence_rank_max is not None:
            casti.append(f"frekvence do stupně {self.frekvence_rank_max}")
        if self.skupina_kod:
            casti.append(f"skupina pacientů: {self.skupina_kod}")
        if self.nazev:
            casti.append(f"název obsahuje „{self.nazev}“")
        if self.kod_sukl:
            casti.append(f"kód SÚKL {self.kod_sukl}")
        if self.ucinna_latka:
            casti.append(f"účinná látka „{self.ucinna_latka}“")
        if self.nazev_vzor is not None:
            casti.append(self.nazev_vzor.popis())
        if self.vek is not None:
            v = (f"{self.vek * 12:.0f} měsíců" if self.vek < 1 else f"{self.vek:g} let")
            casti.append(f"pro dítě {v} (jen léky, jejichž SPC tento věk výslovně připouští)")
        elif self.pro_deti:
            casti.append("pro děti (jen léky, jejichž SPC uvádí dávkování pro děti)")
        return "; ".join(casti) or "bez filtru"


def fields_of(dc):
    import dataclasses
    return dataclasses.fields(dc)


@dataclass
class Vysledek:
    kod_sukl: str
    nazev: str
    sila: str | None
    na_predpis: bool | None    # z API SUKL, ne z SPC
    hrazeno: bool | None       # z API SUKL, seznam scau
    ucinne_latky: list[str] | None
    atc: str | None
    lekova_forma: str | None
    strana_pdf: int | None     # kde to v SPC stoji - pro odkaz do PDF
    sekce: str
    obsah_text: str
    frekvence: str | None
    organovy_system: str | None
    sekce_atributy: dict | None
    cosine: float
    fts: float                 # surova hodnota ts_rank_cd
    poradi_sem: int | None
    poradi_fts: int | None
    rrf: float
    vek_od: float | None = None      # od kolika let (common/vek.py), NULL = nevim
    pro_deti: bool | None = None


@dataclass
class Odpoved:
    dotaz: str
    filtr: Filtr
    vysledky: list[Vysledek] = field(default_factory=list)
    kandidatu_pred_prahem: int = 0
    prah: float = 0.0
    cely_usek: bool = False    # slo o CTENI sekce, ne hledani v ni
    usek_orezan: bool = False  # ...a jeste ho zuzil dalsi filtr

    @property
    def prazdna_kvuli_filtru(self) -> bool:
        """Filtr nepustil dal vubec nic - to se musi uzivateli rict natvrdo,
        vcetne toho, cim se filtrovalo."""
        return self.kandidatu_pred_prahem == 0

    @property
    def prazdna_kvuli_prahu(self) -> bool:
        """Neco se naslo, ale nic dost podobneho."""
        return not self.vysledky and self.kandidatu_pred_prahem > 0


def _podminky(f: Filtr) -> tuple[str, dict]:
    kde, par = [], {}
    if f.sekce:
        kde.append("s.sekce = ANY(%(sekce)s)")
        par["sekce"] = list(f.sekce)
    if f.na_predpis is not None:
        kde.append("l.na_predpis = %(na_predpis)s")
        par["na_predpis"] = f.na_predpis
    # Hrazenost je NEZAVISLA na zpusobu vydeje - lek muze byt na predpis
    # a nehrazeny zaroven (ABLYMICO, AMOKSIKLAV).
    if f.hrazeno is not None:
        kde.append("l.hrazeno = %(hrazeno)s")
        par["hrazeno"] = f.hrazeno
    if f.sila:
        # Sila se pise BEZ mezery, presne jak ji vraci API ("500MG").
        kde.append("upper(replace(l.sila,' ','')) = upper(replace(%(sila)s,' ',''))")
        par["sila"] = f.sila
    if f.atc_prefix:
        kde.append("l.atc LIKE %(atc)s")
        par["atc"] = f.atc_prefix + "%"
    if f.organovy_system:
        kde.append("s.organovy_system = %(soc)s")
        par["soc"] = f.organovy_system
    # PRESNA shoda ma prednost - "vzacne" znamena vzacne, ne "az vzacne".
    if f.frekvence:
        kde.append("s.frekvence = %(frekvence)s")
        par["frekvence"] = f.frekvence
    if f.frekvence_rank_max is not None:
        kde.append("s.frekvence_rank <= %(frank)s")
        par["frank"] = f.frekvence_rank_max
    if f.pro_deti:
        kde.append("l.pro_deti IS TRUE")
    if f.vek is not None:
        kde.append("l.vek_od <= %(vek)s")
        par["vek"] = f.vek
    if f.nazev_vzor is not None and f.nazev_vzor.platny:
        # JEN nazev leku, ne ucinne latky (1. 10. 2026): kombinovane pripravky
        # a vakciny maji desitky latek a vzor se pak chytal skoro vsude.
        podminka, par["vzor"] = f.nazev_vzor.sql()
        kde.append(podminka)
    if f.skupina_kod:
        kde.append("s.sekce_atributy->>'skupina_kod' = %(skup)s")
        par["skup"] = f.skupina_kod
    if f.nazev:
        kde.append("l.nazev ILIKE %(nazev)s")
        par["nazev"] = f"%{f.nazev}%"
    if f.kod_sukl:
        kde.append("l.kod_sukl = %(kod)s")
        par["kod"] = f.kod_sukl
    if f.ucinna_latka:
        kde.append("EXISTS (SELECT 1 FROM unnest(l.ucinne_latky) x "
                   "WHERE x ILIKE %(latka)s)")
        par["latka"] = f"%{f.ucinna_latka}%"
    return (" AND " + " AND ".join(kde) if kde else ""), par


def hledej(dotaz: str, *, filtr: Filtr | None = None, limit: int = 20,
           prah: float = 0.0, vaha_semantika: float = VAHA_SEMANTIKA,
           rrf_k: int = RRF_K, zpusob: str = "rrf",
           puvodni_dotaz: str | None = None,
           dsn: str = PG_DSN) -> Odpoved:
    """Hybridni hledani. Vraci vysledky serazene podle RRF."""
    from common.ollama_client import embed

    f = filtr or Filtr()

    # Kdyz filtr vybral leciva PRESNE (podle nazvu, latky, sily...), prah
    # na podobnost se NEUPLATNUJE. Vyber uz probehl podle rizene hodnoty
    # a cosine by ho jen kazil - viz Filtr.je_presny().
    if prah and f.je_presny():
        logger.debug("prah %.2f se neuplatnuje, filtr je presny", prah)
        prah = 0.0

    # Rozsireni dotazu o formulace, ktere jsou v textech SPC. Zmereno, ze
    # nejlepsi "synonymum" neni odborny termin, ale veta z dokumentu -
    # MAALOX na "mám reflux" #19, na "vracení kyselého obsahu..." #1.
    # Rozsiruje se DOTAZ, do dat se nic nepridava (viz common/dotazy.py).
    varianty = rozsir(dotaz)

    # POJISTKA PROTI OREZANI ROUTEREM. Router neni deterministicky a stejny
    # dotaz z nej vyjde ruzne - "bolí mě zuby" da jednou "bolest zubů",
    # jindy "zuby". A "zuby" ma cosine 0,396, tedy POD prahem, takze se
    # nenajde NIC, prestoze ACIFEIN bolest zubu leci.
    #
    # Puvodni veta uzivatele se proto pridava jako dalsi varianta. Bere se
    # MAXIMUM pres varianty, takze horsi varianta nemuze uskodit - jen
    # zachrani pripad, kdy router ustrihl prilis:
    #     'zuby'  0,396   'bolí mě zuby'  0,845   -> 0,845
    #     'spát'  0,486   'nemůžu spát'   0,587   -> 0,587
    # Puvodni veta se pridava JINAK NEZ slovnikove varianty - viz nize.
    puv = (puvodni_dotaz or "").strip()
    ma_puvodni = bool(puv) and puv not in varianty

    vektory = embed(varianty + ([puv] if ma_puvodni else []), model=MODEL_EMBED)

    kde, par = _podminky(f)
    par.update({"dotaz": dotaz, "n": KANDIDATU})
    for i, v in enumerate(vektory):
        par[f"vek{i}"] = str(v)

    # SLOVNIKOVE varianty: maximum PO RADCICH. Ruzne leky legitimne
    # odpovidaji ruznym formulacim - DITHIADEN sedi na "alergicka reakce"
    # (0,701), ZYRTEC na "uleva od priznaku alergie" (0,699). Kdyby se
    # vybrala jedna varianta globalne, jeden z nich by se ztratil.
    n_var = len(varianty)
    # Kazda varianta se porovnava s OBEMA vektory radku - s textem
    # i s klicem - a bere se lepsi. Klic tim muze jen pomoci: u dotazu
    # na detail z dlouhe vety vyhraje obsah_text, u kratkeho dotazu klic.
    # Radky bez klice maji embedding_klic NULL, proto COALESCE.
    vyrazy = [f"GREATEST(1 - (s.embedding <=> %(vek{i})s::vector), "
              f"COALESCE(1 - (s.embedding_klic <=> %(vek{i})s::vector), -1))"
              for i in range(n_var)]
    cosine_sql = vyrazy[0] if n_var == 1 else f"GREATEST({', '.join(vyrazy)})"

    # PUVODNI VETA: rozhoduje se GLOBALNE, ne po radcich.
    #
    # Je to pojistka pro pripad, kdy router ureze prilis ("bolí mě zuby"
    # -> "zuby", cosine 0,396 misto 0,845). Kdyby ale byla jen dalsi
    # variantou v maximu po radcich, dostal by KAZDY radek jeden pokus
    # navic a mohl by si vybrat tu variantu, ktera mu lichoti. Zmereno
    # na "mám průjem": PARALEN "bolestivá menstruace" si vybral puvodni
    # vetu (0,554 misto 0,535) a preskocil prah, protoze slovo "mám"
    # posouva vektor smerem ke stiznostem.
    #
    # Proto se porovnavaji NEJLEPSI vysledky obou a pouzije se JEN ten
    # lepsi:
    #     'průjem' 0,623  vs  'mám průjem' 0,604   -> router
    #     'zuby'   0,396  vs  'bolí mě zuby' 0,845 -> puvodni veta
    if ma_puvodni:
        cosine_sql = (f"CASE WHEN %(puv_lepsi)s THEN "
                      f"GREATEST(1 - (s.embedding <=> %(vek{n_var})s::vector), "
                      f"COALESCE(1 - (s.embedding_klic <=> %(vek{n_var})s::vector), -1)) "
                      f"ELSE {cosine_sql} END")

    # FULLTEXTOVY DOTAZ: AND uvnitr pojmu, OR mezi pojmy.
    #
    # Do 22.9.2026 slo do fulltextu JEN `dotaz` a cely se prevedl na OR.
    # To melo dve vady, obe zmerene:
    #
    # 1. Slovnikove varianty do fulltextu NESLY VUBEC, pouzivaly se jen
    #    pro vektory. Pritom cely ciselnik byl postaveny tak, aby mapoval
    #    laicky vyraz na FORMULACI Z DOKUMENTU - a presne na to je
    #    fulltext nejlepsi:
    #        dotaz 'rýma'                -> OLYNTH fts =  0,0
    #        dotaz 'zánět sliznice nosu' -> OLYNTH fts = 12,0
    #
    # 2. Plosny OR zahazoval konkretnost. Z variant 'ryma',
    #    'ucpany nos', 'zanet sliznice nosu' vznikl jeden pytel slov,
    #    takze stacilo jedine slovo 'zanet' a radek se pocital jako
    #    shoda. Zmereno na sekci indikace:
    #        jen puvodni 'rýma'                     3 radky
    #        OR mezi vsemi slovy                   43 radku
    #        AND uvnitr varianty, OR mezi nimi      5 radku
    #    Tech 43 obsahovalo OSM ruznych zanetu AMOKSIKLAVU - kosti,
    #    kuze, dutin, prudusek, zubu, ucha, mechyre, ledvin. U dotazu
    #    'zánět kůže' je to jeste vic videt: 43 -> 1.
    #
    # PUVODNI VETA UZIVATELE ZUSTAVA NA OR. Prisny AND na ni pustit
    # NELZE - veta 'mám rýmu' obsahuje i sloveso, takze by se vyzadovalo
    # i 'mít' a nenaslo by se NIC. Rizeny pojem ze slovniku je proti tomu
    # ocisteny, takze u nej AND smysl ma.
    #
    # Prevod na OR se dela nad UZ ZPRACOVANYM tsquery, ne nad textem od
    # uzivatele - websearch_to_tsquery vstup rozparsuje a uvozovkovane
    # fraze necha jako <->, takze zamena '&' za '|' je bezpecna.
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        casti: list[str] = []
        # varianty[0] je puvodni text dotazu -> OR, zbytek jsou rizene
        # pojmy ze slovniku -> AND uvnitr.
        for i, v in enumerate(varianty):
            vyraz = ("replace(websearch_to_tsquery('czech_unaccent', %s)::text, '&', '|')"
                     if i == 0 else
                     "websearch_to_tsquery('czech_unaccent', %s)::text")
            q = cur.execute(f"SELECT {vyraz}", (v,)).fetchone()[0]
            if q:
                casti.append(f"({q})")
        par["fts_dotaz"] = " | ".join(casti)

        # Rozhodnuti, jestli je lepsi puvodni veta nebo text od routeru.
        # Levne - jen dve agregace nad uz vyfiltrovanou mnozinou.
        par["puv_lepsi"] = False
        if ma_puvodni:
            vyrazy_slovnik = (vyrazy[0] if n_var == 1
                              else f"GREATEST({', '.join(vyrazy)})")
            radek = cur.execute(f"""
                SELECT max({vyrazy_slovnik}),
                       max(GREATEST(1 - (s.embedding <=> %(vek{n_var})s::vector),
                           COALESCE(1 - (s.embedding_klic <=> %(vek{n_var})s::vector), -1)))
                FROM leciva_search s JOIN leciva l USING (kod_sukl)
                WHERE s.embedding IS NOT NULL {kde}
            """, par).fetchone()
            if radek and radek[0] is not None and radek[1] is not None:
                par["puv_lepsi"] = float(radek[1]) > float(radek[0])
                logger.debug("puvodni veta lepsi: %s (%.3f vs %.3f)",
                             par["puv_lepsi"], radek[1], radek[0])

    # Dva zebricky zvlast, spojene az v Pythonu - v SQL by to slo taky,
    # ale takhle je videt, ktere poradi kterou polozku vytahlo, a da se
    # to pouzit pri ladeni vah.
    sql = f"""
        WITH zaklad AS (
            SELECT s.id, s.kod_sukl, l.nazev, l.sila,
                   l.na_predpis, l.hrazeno, l.ucinne_latky, l.atc,
                   l.lekova_forma, s.strana_pdf, l.vek_od, l.pro_deti,
                   s.sekce, s.obsah_text,
                   s.frekvence, s.organovy_system, s.sekce_atributy,
                   {cosine_sql} AS cosine,
                   ts_rank_cd(s.search_fts, %(fts_dotaz)s::tsquery) AS fts
            FROM leciva_search s
            JOIN leciva l USING (kod_sukl)
            WHERE s.embedding IS NOT NULL {kde}
        )
        SELECT * FROM zaklad
    """

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, par)
        sloupce = [d.name for d in cur.description]
        radky = [dict(zip(sloupce, r)) for r in cur.fetchall()]

    if not radky:
        return Odpoved(dotaz, f, [], 0, prah)

    # Poradi v obou zebricich
    dle_sem = sorted(radky, key=lambda r: -r["cosine"])[:KANDIDATU]
    dle_fts = [r for r in sorted(radky, key=lambda r: -r["fts"]) if r["fts"] > 0][:KANDIDATU]

    poradi_sem = {r["id"]: i + 1 for i, r in enumerate(dle_sem)}
    poradi_fts = {r["id"]: i + 1 for i, r in enumerate(dle_fts)}

    # Dva zpusoby razeni. Ktery je lepsi, ma rozhodnout EVALUACE,
    # ne odhad - proto jsou tu oba.
    #
    #   "rrf"    klasicka fuze dvou poradi. Fulltext muze zmenit poradi.
    #            Zmereno, ze to jde i proti semantice: MAALOX (cosine 0,48)
    #            skoncil nad ACIFEINEM (0,52), protoze mel lepsi misto ve
    #            fulltextu. Nepomohla vaha 0,95 ani k=5 - RRF pracuje
    #            s poradim, takze i maly prispevek prevrati tesny rozdil.
    #   "cosine" poradi urcuje VYHRADNE podobnost, fulltext slouzi jen
    #            k tomu, aby se kandidat vubec dostal do vyberu (recall).
    #            Odpovida zadani "fulltext je jen doplnek" doslovneji.
    if zpusob == "cosine":
        skore = {r["id"]: float(r["cosine"]) for r in radky
                 if r["id"] in poradi_sem or r["id"] in poradi_fts}
        dle_id = {r["id"]: r for r in radky}
        serazene = sorted(skore.items(), key=lambda kv: -kv[1])
        return _sestav(serazene, dle_id, poradi_sem, poradi_fts,
                       dotaz, f, prah, limit, len(radky))

    # CTENI SEKCE misto hledani v ni.
    # Kdyz uzivatel jmenuje KONKRETNI lek a KONKRETNI sekci ("davkovani
    # zyrtec"), vyber uz udelal filtr a razeni podle podobnosti nema co
    # merit - do vektoru jde jen nazev leku, ktery v textu sekce vubec
    # neni. Zmereno u ZYRTECu: vsech 6 radku davkovani melo cosine
    # 0,320 / 0,307 / 0,303 ..., tedy sum. Nahoru se pak dostalo
    # "davkovani pri tezkem poskozeni ledvin" misto obecneho davkovani.
    #
    # V takovem pripade se vraci CELA sekce v poradi, v jakem stoji
    # v dokumentu - to je to, co clovek chce precist.
    # Router k obsahove sekci casto prida i 'atributy' ("davkovani vibrocil"
    # -> davkovani + atributy, 1. 10. 2026). Cteni sekce se pak nezaplo,
    # nejlepsi pasazi byla identita leku a na davkovani zbyla 2 mista
    # z 5. Lek uz vybral filtr na nazev, atributy jsou tu navic.
    obsahove = [s for s in (f.sekce or []) if s != "atributy"]
    if len(obsahove) == 1 and (f.nazev or f.kod_sukl) \
            and any(r["sekce"] == obsahove[0] for r in radky):
        radky = [r for r in radky if r["sekce"] == obsahove[0]]
        dle_id = {r["id"]: r for r in radky}
        serazene = [(r["id"], 0.0) for r in sorted(radky, key=lambda r: r["id"])]
        odp = _sestav(serazene, dle_id, poradi_sem, poradi_fts,
                      dotaz, f, prah, limit, len(radky))
        odp.cely_usek = True
        # Kdyz sekci zuzil jeste NEJAKY DALSI filtr, uz to CELA sekce
        # NENI a tvrdit to je zavadejici: "caste nezadouci ucinky
        # amoksiklav" vrati 6 polozek ze 44. Razeni podle dokumentu je
        # porad spravne, jen popisek musi rict pravdu.
        odp.usek_orezan = any([f.frekvence, f.frekvence_rank_max,
                               f.skupina_kod, f.organovy_system])
        return odp

    vaha_fts = 1.0 - vaha_semantika
    skore: dict[int, float] = {}
    for rid, poradi in poradi_sem.items():
        skore[rid] = skore.get(rid, 0.0) + vaha_semantika / (rrf_k + poradi)
    for rid, poradi in poradi_fts.items():
        skore[rid] = skore.get(rid, 0.0) + vaha_fts / (rrf_k + poradi)

    dle_id = {r["id"]: r for r in radky}
    serazene = sorted(skore.items(), key=lambda kv: -kv[1])
    return _sestav(serazene, dle_id, poradi_sem, poradi_fts,
                   dotaz, f, prah, limit, len(radky))


def _sestav(serazene, dle_id, poradi_sem, poradi_fts,
            dotaz, f, prah, limit, kandidatu) -> "Odpoved":
    vysledky = []
    for rid, s in serazene:
        r = dle_id[rid]
        # Prah se aplikuje na COSINE, ne na RRF - RRF je jen poradi
        # a jeho hodnota nic nerika o tom, jak moc je vysledek podobny.
        if r["cosine"] < prah:
            continue
        vysledky.append(Vysledek(
            kod_sukl=r["kod_sukl"], nazev=r["nazev"], sila=r["sila"],
            na_predpis=r["na_predpis"], hrazeno=r["hrazeno"],
            ucinne_latky=r["ucinne_latky"], atc=r["atc"],
            lekova_forma=r["lekova_forma"], strana_pdf=r["strana_pdf"],
            vek_od=r.get("vek_od"), pro_deti=r.get("pro_deti"),
            sekce=r["sekce"], obsah_text=r["obsah_text"],
            frekvence=r["frekvence"], organovy_system=r["organovy_system"],
            sekce_atributy=r["sekce_atributy"],
            cosine=float(r["cosine"]), fts=float(r["fts"] or 0.0),
            poradi_sem=poradi_sem.get(rid), poradi_fts=poradi_fts.get(rid),
            rrf=s))
        if len(vysledky) >= limit:
            break

    return Odpoved(dotaz, f, vysledky, kandidatu, prah)


# --- Seskupeni po lecivech --------------------------------------------------
# Tabulka ma jeden radek na POLOZKU, takze Paralen ma vlastni radek pro
# kazdou indikaci. Kdyby se vzalo top-10 radku, mohlo by to byt osm radku
# Paralenu a dva Panadolu - misto deseti ruznych leku. Uzivatel pritom
# ceka seznam LEKU, ne seznam pasazi.
#
# Proto se hleda s REZERVOU (vic radku, nez kolik leku se ma vratit)
# a teprve pak se seskupuje. Dedu­plikace tedy neni jen vec zobrazeni,
# ale ovlivnuje i to, kolik radku se tahne z databaze.

# Cisla bodu SPC - pro odkaz do dokumentu.
CISLO_SEKCE = {"indikace": "4.1", "davkovani": "4.2",
               "kontraindikace": "4.3", "nezadouci_ucinky": "4.8"}

NAZEV_SEKCE = {"indikace": "Terapeutické indikace",
               "davkovani": "Dávkování a způsob podání",
               "kontraindikace": "Kontraindikace",
               "nezadouci_ucinky": "Nežádoucí účinky",
               "atributy": "identita léku (z API SÚKL)"}


@dataclass
class LecivoVysledek:
    """Jeden LEK s nejlepsi pasazi jako dukazem, proc se trefil."""
    kod_sukl: str
    nazev: str
    sila: str | None
    nejlepsi: "Vysledek"
    dalsi: list["Vysledek"] = field(default_factory=list)

    @property
    def skore(self) -> float:
        return self.nejlepsi.rrf

    @property
    def pasazi(self) -> int:
        return 1 + len(self.dalsi)

    def odkaz(self, adresar: str | None = None) -> str:
        """Doklad puvodu: cesta k dokumentu + nazev sekce.

        Ve fazi CMD se v terminalu klikat neda, ale je to dohledatelne.
        Ve fazi GUI se z toho udela kotva #page=N.
        """
        sekce = self.nejlepsi.sekce
        if sekce == "atributy":
            return f"API SÚKL, kód {self.kod_sukl}"
        adr = adresar or f"data/leciva/{self.kod_sukl}_*"
        cislo = CISLO_SEKCE.get(sekce, "")
        return f"{adr}/spc.md § {cislo} {NAZEV_SEKCE.get(sekce, sekce)}"


def seskup(vysledky: list["Vysledek"], *, leciv: int = 10,
           pasazi_na_lecivo: int = 3, abecedne: "bool | dict" = False) -> list[LecivoVysledek]:
    """Seskupi radky po lecivech. Poradi leku urcuje jeho NEJLEPSI pasaz.

    abecedne=True: dotaz byl JEN vzor nazvu („lek zacina oxy") - semantika
    nema co merit a poradi podle skore by bylo nahodne.
    """
    podle_leku: dict[str, list[Vysledek]] = {}
    for v in vysledky:
        podle_leku.setdefault(v.kod_sukl, []).append(v)

    ven = []
    for kod, polozky in podle_leku.items():
        polozky.sort(key=lambda v: -v.rrf)
        ven.append(LecivoVysledek(
            kod_sukl=kod, nazev=polozky[0].nazev, sila=polozky[0].sila,
            nejlepsi=polozky[0], dalsi=polozky[1:pasazi_na_lecivo]))

    if isinstance(abecedne, dict):
        # „lek priblizne XXX": nejpodobnejsi nazev nahore, pak abecedne
        ven.sort(key=lambda l: (-abecedne.get(l.kod_sukl, 0.0), l.nazev or "", l.sila or ""))
    elif abecedne:
        ven.sort(key=lambda l: (l.nazev or "", l.sila or ""))
    else:
        ven.sort(key=lambda l: -l.skore)
    return ven[:leciv]


def je_abecedne(filtr: "Filtr | None") -> bool:
    """Radit vysledek abecedne? (jen vzor nazvu, zadny dalsi text)"""
    v = getattr(filtr, "nazev_vzor", None)
    if v is not None and v.platny and v.jen_vzor and v.druh == "priblizne":
        return v.podobnost or {}          # radit podle podobnosti nazvu
    return bool(v is not None and v.platny and v.jen_vzor)
