"""Hledani podle CASTI nazvu: „lek zacina oxy", „lek obsahuje pox", „lek konci prazol".

PROC: laik si cast nazvu pamatuje, cely ne. Semantika (vektory) to neumi -
embedding zachycuje vyznam slova, ne jeho pismena, a „oxy" vyznam nema.
Je to uloha NA PISMENA, proto deterministicky filtr nad nazvem a latkami.

Rozhodnuto 1. 10. 2026: jen PEVNE formulace, zadne „neco jako" - aby se
nemotalo s beznymi vetami („neco na rymu"):

    lek zacina [na] XXX     ->  nazev leku ZACINA na XXX
    lek obsahuje XXX        ->  nazev leku OBSAHUJE XXX
    lek konci [na] XXX      ->  nazev leku KONCI na XXX
    lek priblizne XXX       ->  nazev leku se PODOBA XXX (preklepy, fonetika:
                                „zirtek" -> ZYRTEC, „oxicilin" -> OXACILIN)

XXX musi mit aspon 3 znaky. Hleda se JEN v NAZVU leku, ne v ucinnych
latkach (1. 10. 2026): kombinovane pripravky a vakciny maji desitky latek
a vzor se pak chytal skoro vsude. Bez ohledu na velikost pismen
a diakritiku (v SQL `bez_diakritiky`).

Zbytek dotazu jde do semantiky: „lek zacina oxy na rymu" = vzor + „na rymu".
Stejny princip jako vek (common/vek.py): rozpozna se pred routerem nezavisle
na modelu, protoze router je nedeterministicky.
"""

import re
from dataclasses import dataclass

MIN_DELKA = 3

_VZOR = re.compile(
    r"\b(?:lék|lek|léky|leky|léků|leku|léčivo|lecivo|přípravek|pripravek)\s+"
    r"(?P<druh>začíná|zacina|začínající|zacinajici|obsahuje|obsahující|obsahujici|"
    r"končí|konci|končící|koncici|přibližně|priblizne)\s+(?:na\s+)?(?P<text>[^\s,;.!?]+)",
    re.IGNORECASE)

_DRUH = {"zač": "zacina", "zac": "zacina", "obs": "obsahuje", "kon": "konci",
         "při": "priblizne", "pri": "priblizne"}
POPIS = {"zacina": "začíná na", "obsahuje": "obsahuje", "konci": "končí na",
         "priblizne": "se přibližně jmenuje"}

# --- „lek priblizne XXX": preklepy a foneticky zapis -------------------------
# Laik pise jak slysi: „zirtek" (ZYRTEC), „oxicilin" (OXACILIN), „nurophen".
# Trigramy (pg_trgm) radi spatne – „oxicilin" dal AMPICILINU i PENICILINU
# 0,56 a OXACILINU 0,50 (spolecna koncovka -icilin). Proto: foneticka
# normalizace obou stran + podobnost po SLOVECH nazvu (difflib), v Pythonu
# nad par tisici unikatnich slov - milisekundy, bez pluginu.
PRAH_PODOBNOSTI = 0.75      # oxicilin->oxacilin 0,88; ampicilin 0,71 uz ne
_FONETIKA = [("ph", "f"), ("th", "t"), ("ck", "k"), ("qu", "kv"), ("x", "ks"),
             ("y", "i"), ("w", "v"), ("c", "k")]
_SLOVA_NAZVU: dict[str, set[str]] | None = None     # normalizovane slovo -> kody


def foneticky(s: str) -> str:
    import unicodedata
    t = "".join(z for z in unicodedata.normalize("NFD", (s or "").lower())
                if unicodedata.category(z) != "Mn")
    for a, b in _FONETIKA:
        t = t.replace(a, b)
    return t


def _slova_nazvu() -> dict[str, set[str]]:
    """Index: foneticky normalizovane slovo nazvu -> kody zastupcu. Jednou."""
    global _SLOVA_NAZVU
    if _SLOVA_NAZVU is None:
        import psycopg
        from common.config import PG_DSN
        idx: dict[str, set[str]] = {}
        with psycopg.connect(PG_DSN) as c:
            for kod, nazev in c.execute(
                    "SELECT kod_sukl, nazev FROM leciva WHERE coalesce(zastupce, true)"):
                slova = re.findall(r"[a-z0-9]+", foneticky(nazev))
                # Jednotliva slova + SPOJENE tvary (dvojice sousednich slov
                # a cely nazev bez mezer/spojovniku): „oftalmoframikoin"
                # i „oftalmo-framikoin" -> OPHTHALMO-FRAMYKOIN (1. 10. 2026).
                tvary = set(slova)
                tvary.update(a + b for a, b in zip(slova, slova[1:]))
                tvary.add("".join(slova))
                for w in tvary:
                    if len(w) >= MIN_DELKA:
                        idx.setdefault(w, set()).add(kod)
        _SLOVA_NAZVU = idx
    return _SLOVA_NAZVU


def podobne_kody(text: str) -> dict[str, float]:
    """kod -> podobnost (0-1) leku, jehoz nejake slovo nazvu se podoba textu."""
    from difflib import SequenceMatcher
    q = re.sub(r"[^a-z0-9]", "", foneticky(text))     # bez mezer a spojovniku
    ven: dict[str, float] = {}
    for w, kody in _slova_nazvu().items():
        if abs(len(w) - len(q)) > max(3, len(q) // 2):
            continue
        s = SequenceMatcher(None, q, w).ratio()
        if s >= PRAH_PODOBNOSTI:
            for k in kody:
                ven[k] = max(ven.get(k, 0.0), s)
    return ven


@dataclass
class NazevVzor:
    druh: str            # zacina | obsahuje | konci
    text: str            # co uzivatel napsal (bez zmeny)
    platny: bool         # aspon MIN_DELKA znaku
    jen_vzor: bool = False   # dotaz NENI nic jineho nez vzor -> radit abecedne
    podobnost: dict | None = None   # u „priblizne": kod -> podobnost (razeni)

    def sql(self) -> tuple[str, str]:
        """(podminka nad bez_diakritiky(l.nazev), parametr).

        „konci" = KONEC SLOVA v nazvu, ne konec celeho nazvu: nazvy koncí
        vyrobcem („OMEPRAZOL TEVA") a „lek konci na prazol" by jinak nenasel
        nic. Regex \\M = konec slova (PostgreSQL), text jen pismena a cislice.
        """
        if self.druh == "priblizne":
            if self.podobnost is None:
                self.podobnost = podobne_kody(self.text)
            return ("l.kod_sukl = ANY(%(vzor)s)", list(self.podobnost))
        if self.druh == "konci":
            t = re.sub(r"[^0-9A-Za-zÀ-ž]", "", self.text)
            return ("bez_diakritiky(l.nazev) ~* (bez_diakritiky(%(vzor)s) || '\\M')", t)
        return ("bez_diakritiky(l.nazev) ILIKE bez_diakritiky(%(vzor)s)", self.like())

    def like(self) -> str:
        """Vzor pro ILIKE (text se porovnava bez diakritiky na strane SQL)."""
        t = self.text.replace("%", "").replace("_", "")
        return {"zacina": f"{t}%", "obsahuje": f"%{t}%", "konci": f"%{t}"}[self.druh]

    def popis(self) -> str:
        if not self.platny:
            return (f"vzor „{POPIS[self.druh]} {self.text}“ NEPOUŽIT – potřeba "
                    f"aspoň {MIN_DELKA} písmena")
        if self.druh == "konci":
            return f"slovo v názvu léku končí na „{self.text}“"
        if self.druh == "priblizne":
            return f"název léku se přibližně podobá „{self.text}“ (i s překlepem)"
        return f"název léku {POPIS[self.druh]} „{self.text}“"


def vzor_z_dotazu(dotaz: str) -> NazevVzor | None:
    """Pevna formulace v dotazu, nebo None.

    'lék začíná oxy'            -> zacina 'oxy'
    'lék začíná na oxy na rýmu' -> zacina 'oxy'
    'lék obsahuje pox'          -> obsahuje 'pox'
    'lék končí na prazol'       -> konci 'prazol'
    'lék začíná ox'             -> zacina 'ox', platny=False
    'něco na rýmu'              -> None
    """
    m = _VZOR.search(dotaz or "")
    if not m:
        return None
    text = m.group("text").strip("„“\"'*…")
    druh = _DRUH[m.group("druh")[:3].lower()]
    return NazevVzor(druh, text, len(text) >= MIN_DELKA)


def bez_vzoru(text: str) -> str:
    """Dotaz bez formulace vzoru - zbytek jde do semantiky."""
    t = _VZOR.sub(" ", text or "")
    return re.sub(r"\s+", " ", t).strip(" ,;.")
