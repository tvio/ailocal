# STAV K 7.10.2026 — ÚKLID HOTOVÝ, DOKUMENTACE V `docs/` PROJITÁ PROTI KÓDU

- **7. 10.:** `docs/` aktualizované (hledání přepsáno celé, GUI/API, věk,
  Batch, scénáře přeměřené přes API – 55 dotazů). Oprava v hledání:
  původní věta už nenese věk do vektoru. Evaluace 18/20, 69 %, 5/6.
- Hledání zrychleno: z DB jdou jen kandidáti (NÚ napříč trhem 25 → 6 s,
  všechny sekce 13 → 5 s). „Pro děti" bez věku už nevrací léky od 18 let.
- Výraz `kocovin` v hledacím slovníku záměrně není – přidává se naživo
  při prezentaci (scénáře kap. 7).
- **Rozdělování zátěže mezi stroje s Ollamou** je hotové a ověřené
  simulací; druhý stroj (Dell 10.6.38.9) ještě nemá otevřený port, až
  ho mít bude, zapojí se sám (`docs/provoz_pristupy.md`).
- **API po těchto změnách restartovat.**
- Změny od commitu `5759433` (přejmenování skriptů, dokumenty) jsou
  připravené k zápisu, necommitnuté.

Níže stav z 6. 10. večer:


**Nic neběží na pozadí.** Další krok: kontejner a nasazení na server
(`todo.md` TOP 3 a 4).

- **Struktura:** v kořeni 12 skriptů (`extrakce_1…6`, `extrakce_all.py`,
  `hledani_cli/log/evaluace.py`, `api.py`, `provoz_priprava.py`) + soubory,
  do kterých se zapisuje (`poznatky.md`, `aktualnistav.md`, `todo.md`,
  `CLAUDE.md`, `README.md`, `agents.md`). Popisy v `docs/`, benchmarky
  v `benchmarky/`. Dřívější názvy skriptů: `docs/pipeline_prehled.md` oddíl 6.
- **Pipeline:** `extrakce_all.py` (`--seznam`, `--stav`, `--vse`, `--od`,
  `--jen`). Krok 3 umí i `--local` (Ollama) pro jeden lék / malou dávku.
  Celé `--vse` po úklidu puštěné NEBYLO (peníze, hodiny, TRUNCATE DB) –
  vyzkoušen `--stav`, krok rejstřík a lokální extrakce 1 sekce v testu.
- **Smazáno:** stará pipeline nad 32 léky, `legacy/`, `data/leciva/`,
  zastaralé benchmarky a dokumenty (`zadani.md`, `tentoTyden.md`…).
  Kontroly extrakce jsou v `nerealizovane_kontroly/` a neběží.
- **Klíč OpenAI:** `key.yaml` v kořeni, běh ho ověří hned na začátku.
- **Hledání:** slovník dotazů v DB + úprava z GUI, filtr „pro dospělé"
  (od 12 let nebo bez údaje o věku), shoda schovaná u čtení sekce
  a u dotazů jen z atributů. Evaluace po úklidu 18/20, 69 %, 5/6.
- **Stav dat:** konverze 5 897 SPC ok, extrakce 23 495 sekcí hotovo
  (utraceno 11,00 $ ze stropu 11,50 $), DB 8 778 kódů / 472 844 řádků,
  všechny s vektorem.
- **Otevřené:** evaluace 18/20 místo 20/20 („kašlu…", „pálí mě při
  močení") a tři chyby u COLDREXu – `todo.md` TOP 0; API po změnách
  z 6. 10. restartovat.

---

# STAV K 4.10.2026 — INDIKACE PŘEEXTRAHOVANÉ (PROMPT V2), V DB I S VEKTORY

- Cloud doběhl: 23 495 hotovo, 0 chyb, utraceno 11,00 $ (strop 11,50 $).
  Nic neběží, ve frontě nic není.
- DB: `--obnov-sekci indikace` → 25 097 řádků, všechny s vektorem.
- `hledani_evaluace.py --korpus`: parafráze **18/20** (dřív 20/20), přesnost
  69 %, negativní 5/6. Cílové případy (SIMVASTATIN „diabetem mellitem")
  opravené. Čísla v `poznatky.md` 4. 10.
- **Další krok:** `todo.md` TOP „0. Evaluace po indikacích v2" – zjistit,
  proč „kašlu…" a „pálí mě při močení" dávají 0/5. API restartovat.

---

# STAV K 30.9.2026 večer — VĚK POUŽITÍ + DÁVKOVÁNÍ BEZ OŘEZU

- **Ořez 4.2 vypnut** (zahazoval dávky u 56 % SPC, např. VIBROCIL).
  Přeextrahováno 5 451 dávkování (schéma u dávkování vždy). Běží
  `--znovu-chybne --beh` (69 + 8 z dávky 85). **Pak:**

      uv run python extrakce_3_json.py --znovu-chybne --beh   # zbylé chyby
      uv run python extrakce_4_db.py --obnov-sekci davkovani           # + přepočet věku
      uv run python extrakce_5_embeddingy.py                           # jen nové řádky
      # restart API

- **Věk použití** (`common/vek.py`): `leciva.vek_od/pro_deti`, filtr
  „pro děti / pro dítě X let" v routeru (deterministicky), GUI detail
  „Věk použití". Věk určen u 87 % SPC. Poznatky 30. 9. večer.
- **Rejstřík:** `data/leky/<NÁZEV SÍLA>_<kód>` → složka SPC,
  `extrakce_6_rejstrik.py --najdi vibrocil`.
- **Evaluace trhu:** `hledani_evaluace.py --korpus` (parafráze ATC 20/20, 67 %).
- **GUI stránkování** okénkem + výběr 10/25/50/100.
- Utraceno celkem ~10,1 $ (strop 10,5 $).

---

# STAV K 30.9.2026 ráno — CLOUDOVÁ EXTRAKCE KORPUSU DOKONČENA

- `extrakce_3_json.py --beh` doběhl: **23 479 sekcí hotovo, 16 chyb**
  (nevalidní JSON, nejspíš useknutý výstup), 25 bez sekce. Výstupy jsou v
  `data/spc/<slozka>/json/`, report v `data/spc/_extrakce/report.md`.
- **Utraceno 7,94 $** (odhad 5,5 $, výstup byl o 62 % větší). Na účtu
  zbývá ~2 $.
- 16 chyb = zacyklení modelu → opraveno (strop 40 k, teplota 0,4,
  Structured Outputs na 3. pokus), **všech 23 495 hotovo, 0 chyb**.
- **DB: `extrakce_4_db.py --korpus`** (nové) – všech 8 778 kódů v `leciva`
  (sloupce `spc`, `zastupce`), extrakty a hledací řádky JEN JEDNOU ZA SPC
  u zástupce (nejmenší kód). Řádek `atributy` nese názvy a síly všech
  balení SPC. API: PDF přes mapu kód → SPC, výpis léků jen zástupci.
  Staré DB 32 léčiv se tím smaže (TRUNCATE).
- **HOTOVO (30. 9.):** `extrakce_4_db.py --korpus` (37 min) + `extrakce_5_embeddingy.py`
  (~2 h): **451 186 hledacích řádků, všechny s vektorem, 93 507 s klíčem**.
  `hledani_cli.py "mám reflux"` funguje nad korpusem (MAALOX, RELUMO/omeprazol…).
  `hledani_cli.py` ukazuje zdroj z `data/spc/` (opraveno).
- **Po nahrání:** `hledani_evaluace.py` je postavený na 32 léčivech –
  `vzorek_eval.json` má texty staré qwen extrakce a kódy, které nemusí
  být zástupci. Čísla nebudou porovnatelná → evaluaci postavit znovu
  nad korpusem (`todo.md`). Restartovat API (nové sloupce, PDF z `data/spc`).

---

# STAV K 29.9.2026 — EXTRAKCE ZMAPOVANÁ (`docs/pipeline_extrakce.md`)

- Úkol 1 z `todo.md` hotový: celá extrakce a navazující kroky popsané
  v **`docs/pipeline_extrakce.md`**, nálezy N1–N12 v kap. 7. Kód se neměnil.
- **KONTROLY EXTRAKCE DOČASNĚ VYPNUTÉ** (`config.KONTROLY_ZAPNUTE =
  False`): `klic_ma_oporu`, kroky 4a/4b v `pipeline.py`, kontrola
  slovníku modelem. Jednorázově zapnout: `pipeline.py --vse --s-kontrolami`.
  Popis všech kontrol a toho, co chybí (N1–N5, N8, regresní sada):
  **`nerealizovane_kontroly/kontroly_popis.md`**. Zapracovat až nad novým korpusem.
  Důvod: zbývá tento týden, Batch API (okno 24 h) zabere ~2 dny.
- Sekce nového korpusu budou ve stavu `neovereno`. `extrakce_4_db.py`
  (bez `--jen-ok`) je nahraje.
- **N11 rozhodnuto: extrakce do cloudu CELÁ** (luna, reasoning `none`,
  `temperature=0`, `seed=42`). Cloudová cesta je v `common/extrakce.py`.
- **Cena: ~5,5 $ přes Batch** (vstup 31,5 M tok, výstup ~15,7 M;
  pesimisticky 6,4 $). Reálná ukázka na 3 SPC bez chyby. Detaily jsou v
  `poznatky.md` 29. 9., nástroj `benchmarky/extrakce_cloud/`.
- **Otevřené před během:** generovaný slovník přepisuje lunu (42 %
  laických tvarů, i s překlepy). Návrh je brát jen ruční slovník. Dál
  ověřit zůstatek na OpenAI.
- **Generovaný slovník qwenu SMAZÁN** (`slovnik_pojmu.json/.md`, jsou v gitu).
  Platí jen ruční `slovnik_rucni.json`; generovaný se postaví z výstupu luny.
- **`extrakce_3_json.py` hotový a otestovaný** (Batch API, stav v
  SQLite, log, `report.md`, opakování chybných, rozpočtový strop,
  srovnání se sirotčími dávkami). Test na 5 SPC s úmyslnými chybami
  prošel – `poznatky.md` 29. 9. večer.
- **ROZPOČET:** na účtu 10 $, korpus ~5,5 $ (pesimisticky 6,4 $) →
  `config.CLOUD_STROP_USD = 8.0`, stačí na celý korpus s rezervou.
- **Další krok – ostrý běh (v popředí):**

      uv run python extrakce_3_json.py --beh --max-davek 1   # pilot 1000 požadavků
      uv run python extrakce_3_json.py --beh                 # zbytek, naváže
      uv run python extrakce_3_json.py --stav                # kdykoli: souhrn + report.md

  Log: `data/spc/_extrakce/log/`, report: `data/spc/_extrakce/report.md`.

---

# STAV K 25.9.2026 večer — KONVERZE A SEKCE CELÉHO KORPUSU HOTOVÉ

**Nic neběží na pozadí.** Po restartu počítače lze navázat. Další krok:
**extrakce do JSON modelem** – plán a pod-úkoly v `todo.md` úplně nahoře
(úterý 29. 9.).

## Kde jsou data

| co | kde |
|---|---|
| seznam léčiv (zářijové vydání SÚKL) | `data/pool_leciv.json` + `.meta.json` (vydání) |
| plné detaily kódů v rozsahu | `data/detaily_leciv/<kód>.json` (9 196) |
| hrazené, číselník látek | `data/hrazene_scau.json`, `data/ciselnik_latky.json` |
| SPC (PDF, md, strany, kontrola, sekce) | `data/spc/<identita>/` |
| stav inventáře a konverze | `data/spc/_stav.sqlite` (tabulky `kody`, `spc`) |
| **reporty k prohlédnutí** | `data/spc/_report/podezrele.html` (395 podezřelých), `sekce.html` + `sekce.csv` (zdroj každé sekce, nenalezené) |

## Čísla

    kódy v rozsahu (obchodované, PLATNE_STAVY R B C F I K M Y)  8 863
      z toho se SPC                                              8 778
      bez SPC (F/I neregistrované, SPC nemají)                      85
      homeopatika bez SPC (V12) – vynechána                        333
    unikátní SPC používaná kódy                                  5 880
    převedeno (Docling Serve + 4 z Wordu)                  všechna, 0 chyb
    podezřelých po kontrole konverze                               395
    sekcí 4.1/4.2/4.3/4.8                                       23 520
      zdroj Docling (md) / surový text PDF             17 856 / 5 641
      nenalezeno (indikace 13, dávkování 5, kontraindikace 3, NÚ 2)  23

## Jak znovu spustit (měsíční běh = týž příkaz)

    uv run python extrakce_1_konverze.py --obchodovana   # seznam -> inventář -> konverze -> kontroly -> report
    uv run python extrakce_1_konverze.py --stav          # souhrn, podezřelé, kde se stálo
    uv run python extrakce_2_sekce.py --korpus         # sekce + přehled sekcí
Docling Serve přes SSH tunel na `localhost:5001` (musí běžet).

## Co se dnes (25. 9.) změnilo – podrobně v `poznatky.md`

- `extrakce_1_konverze.py`: seznam léčiv z VEŘEJNÉHO API na začátku běhu
  (`common/seznam_leciv.py`, jen při novém měsíčním vydání), inventář s
  deduplikací (EU podle registračního čísla), prokládání 1 EU / 10 CZ,
  EMA ≥ 10 s + Retry-After, opakování při 502/503/504, Word (.doc) přes
  MS Word -> DOCX + PDF, kontroly po každém dokumentu, report na konci.
- `common/kontrola_konverze.py`: frekvence proti značkám PDF (jinak
  geometrie), hledání sekcí SDÍLENÉ s `common/sekce.py`, pokrytí jen
  u sekcí, které extrakce opravdu bere z Doclingu (`zdroj_48`).
- `common/sekce.py`: nadpis „4. 8." s mezerou (MENOPUR).
- `extrakce_2_sekce.py --korpus` + `common/report_sekce.py`.

## Pozor / otevřené

- **Reporty podezřelých ještě nikdo neprošel** – projít podle typu důvodu.
- `pipeline.py` o nových krocích neví; `extrakce_4_db.py` čte zatím
  `data/leciva/…/api.json` (32 léčiv) – viz `todo.md` „Krok 0 – úklid".
- Kontrola konverze nemá regresní sadu (todo) – po každé její změně
  ověřit aspoň ERMM-1, PARALEN, CAVINTON (ok) a MENOPUR, AUBAGIO,
  CASARO (podezřelé).
- Homeopatika a F/I bez SPC: do přehledu patří jen s atributy – todo.

---
