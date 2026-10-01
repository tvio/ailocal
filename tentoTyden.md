# Plán od 2. 10. 2026

Stav: korpus 5 880 SPC je v DB (451 186 řádků s vektory), hledání funguje
včetně věku a hledání podle názvu. Commit `688389b` (větev v1.5).
Podrobnosti a zaškrtávání v `todo.md` nahoře.

## 1. Pipeline pro opakované spouštění (měsíční job)

Jeden příkaz, který projde celý řetěz a jde pustit znovu (přírůstkově,
s navázáním po pádu). Kroky dnes existují jako samostatné skripty:

    seznam léčiv + inventář + konverze   konvertuj_serve.py --obchodovana
    sekce                                extrahuj_sekce.py --korpus
    extrakce (cloud, Batch)              extrahuj_json_cloud.py --beh
    DB                                   naplni_db.py --korpus | --obnov-sekci
    věk                                  (součást naplni_db, --jen-vek)
    embeddingy                           vytvor_embeddingy.py (jen chybějící)
    rejstřík pro člověka                 postav_rejstrik.py
    evaluace                             evaluate.py --korpus

Co chybí:
- **Přírůstek v DB:** `naplni_db.py --korpus` maže vše (TRUNCATE) →
  nahrávat jen nová/změněná SPC, zaniklá označit (nemazat).
- **Změněná SPC:** poznat podle identity dokumentu + otisku PDF; jen ta
  poslat znovu do extrakce (`--znovu-seznam`).
- **Konfigurace místo natvrdo:** Ollama (`ollama_client.KANDIDATI`),
  Docling Serve, Postgres, OpenAI klíč, rozpočet → proměnné prostředí.
- `pipeline.py` / `extrakce_all.py` jako JEDEN seznam kroků (CLAUDE.md),
  zámek, log běhu, souhrn JSON, návratový kód pro cron.

## 2. Úklid projektu

- Benchmarky z kořene do `benchmarky/<téma>/` (bench_*.py, bench_*.json).
- **`.gitignore` ignoruje celé `benchmarky/`** → skripty v něm nejsou
  v gitu. Ignorovat jen jejich výstupy.
- Staré úložiště `data/leciva/` (32 léčiv) a kód, který ho čte
  (`extrahuj_json.py`, `ocisti_json.py`, `zkontroluj_*`, `postav_slovnik.py`,
  `rozdel_vycty.py`) – přepnout na korpus, nebo označit jako legacy.
- `pipeline.py` KROKY a `skripty.md` A→Z přepsat podle skutečnosti.
- Zastaralé dokumenty (`agents.md`, `codex_pripominky.md`, starší části
  `aktualnistav.md`) – projít, co ještě platí.

## 3. Kontejner

- **Nejdřív změřit velikost** `data/spc`, `data/detaily_leciv` a DB.
- Dockerfile aplikace (API + skripty pipeline), `docker-compose` s
  Postgresem (vlastní image s hunspell-cs už existuje).
- **Data mimo git:** `data/` jako volume / bind mount, přenos na server
  balíkem (tar/rsync), ne přes git.
- **DB přenést dumpem** (`pg_dump` / `pg_restore`) – rychlejší než
  znovu počítat embeddingy (~2 h).
- Tajnosti (OpenAI klíč, hesla) mimo image – env / secret soubor.
- Externí služby (Ollama, Docling Serve na DGX) zůstávají mimo kontejner,
  adresy z konfigurace.

## 4. Nasazení na server

- Přenést image + data + dump, nastavit konfiguraci, spustit.
- Smoke test: `hledej.py "mám reflux"`, `evaluate.py --korpus`, GUI.
- Měsíční běh: cron + zámek + upozornění (viz `todo.md` CÍLOVÝ STAV).

## 5. Když zbude čas

- **Slovník dotazů v GUI** (editace hesel) + doplnit podle korpusu.
- **Evaluace:** sada dotazů na věk („pro dítě X let"), rozšířit ATC
  seznamy v `PARAFRAZE_KORPUS`, test 0 pro korpus (pokrytí jen u zástupců).
