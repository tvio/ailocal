# Přístupy

Lokální vývojové prostředí. Hesla níž jsou **záměrně triviální** a jsou už
tak vidět v `docker-compose.yml`, který je v gitu — nic tajného tu nepřibývá.
Skutečné tajemství (klíč k OpenAI) v tomhle souboru **není**, jen odkaz
na to, kde leží.

---

## pgAdmin

http://localhost:5050

| | |
|---|---|
| e-mail | `admin@localsemantic.cz` |
| heslo | `admin` |

Server **localsemantic-postgres** je předkonfigurovaný přes
`pgadmin-servers.json`, po přihlášení je rovnou v seznamu. Heslo si bere
z `pgpass`, takže se na něj nemá ptát.

**POZOR:** uvnitř pgAdminu je hostname **`postgres`**, ne `localhost` —
pgAdmin se připojuje zevnitř sítě kontejnerů. Při ručním zakládání
spojení by `localhost` neprošel.

---

## PostgreSQL

Z hostitele (DBeaver, psql, aplikace):

| | |
|---|---|
| host : port | `localhost:5432` |
| databáze | `localsemantic` |
| uživatel | `localsemantic` |
| heslo | `localsemantic` |

DSN je v `common/config.PG_DSN`, nikde se nepíše natvrdo.

### Role readonly

| | |
|---|---|
| uživatel | `readonly` |
| heslo | `readonly` |

Má jen `SELECT`, a to i na tabulky, které teprve vzniknou
(`ALTER DEFAULT PRIVILEGES`). Na prohlížení bez rizika přepsání
a jako sandbox pro případný Text-to-SQL.

### psql v kontejneru

    docker exec -it localsemantic-postgres psql -U localsemantic -d localsemantic

### Tabulky

| tabulka | co v ní je |
|---|---|
| `leciva` | relační data z API SÚKL |
| `extrakty` | výsledek extrakce sekce (1:N — víc modelů na tutéž sekci) |
| `leciva_search` | jeden řádek = jedna hledatelná položka, embedding + FTS |
| `extrakce_stav` | co se povedlo a co ne (viz `docs/pipeline_stavy.md`) |
| `slovnik_pojmu` | odborný termín → laický tvar (od 29. 9. se neplní) |
| `slovnik_dotazu` | hledací slovník: výraz uživatele → formulace z indikací; mění se z GUI, plnění korpusu ho nemaže |
| `beh_log` | detailní log běhů jednotlivých kroků |

---

## Ollama

Stroje jsou v `common/config.OLLAMA_UZLY` **v pořadí priority**
(na serveru proměnná prostředí `OLLAMA_UZLY`):

| název | adresa | stav 7. 10. 2026 |
|---|---|---|
| `spark` | `http://10.6.38.10:11434` | DGX Spark, hlavní – běží |
| `dell` | `http://10.6.38.9:11434` | Dell se stejným jádrem – **port Ollamy zatím není otevřený** |
| `lokalni` | `http://127.0.0.1:11434` | Ollama na stroji s aplikací (vývoj) |

Bez autentizace. Modely: `gemma4:26b` (router), `bge-m3` (embedding) –
ty dva stačí pro provoz hledání. `qwen3.5:122b` jen pro lokální extrakci
(`--local`).

### Víc strojů: dostupnost a rozdělování zátěže

`common/ollama_client.py` posílá každý dotaz na router i na embedding
na jeden ze strojů:

1. **Jen na dostupné.** Dostupnost hlídá vlákno na pozadí každých 15 s
   (`/api/version`). Stroj, který neběží, se přeskočí; až naběhne,
   zapojí se sám – aplikaci není potřeba restartovat.
2. **Priorita.** Dokud má první stroj volno, jde všechno na něj. Druhý se
   použije, až když první právě vyřizuje dotaz.
3. **Když mají práci všechny,** jde dotaz tam, kde je kratší fronta.
4. **Výpadek uprostřed dotazu:** stroj se hned označí jako nedostupný
   a dotaz se zopakuje na dalším, uživatel nic nepozná. Totéž když stroj
   neodpoví do 30 s (`HLEDANI_TIMEOUT_S`) nebo na něm model chybí.
5. **Modely v paměti:** hlídač drží router i embedding nahrané na všech
   dostupných strojích, takže ani po noční pauze první dotaz nečeká.

**Vytížení stroje Ollama nehlásí** – `/api/ps` říká jen, které modely
jsou v paměti, žádnou frontu ani zatížení. Aplikace si proto sama počítá,
kolik dotazů na kterém stroji právě běží. Vidí tedy jen vlastní zátěž:
o práci, kterou na stroj posílá někdo jiný (extrakce, jiný proces API),
neví. Pozná se jen podle delší odezvy.

**Stav strojů:** `GET /api/stav` → pole `uzly` (dostupnost, rozpracované
dotazy, vyřízeno, selhalo, průměrná odezva, modely v paměti).

**Proč to je potřeba** (změřeno 7. 10. na samotném Sparku,
`benchmarky/soubeh/bench_soubeh.py`): Ollama vyřizuje dotazy na router
**po jednom**. Jeden dotaz 1,6 s, 2 současně 3,0 s, 4 = 6,1 s, 8 = 11,6 s;
celé hledání 8 lidí naráz = poslední čeká 13,8 s. Druhý stroj frontu půlí.

### Co udělat na druhém stroji (Dell), až bude síťově dostupný

1. Ollama musí poslouchat na síti: `OLLAMA_HOST=0.0.0.0:11434` a otevřený
   port 11434 pro server s aplikací.
2. Stáhnout **stejné tagy modelů** jako na Sparku: `ollama pull gemma4:26b`,
   `ollama pull bge-m3`. Jiná verze `bge-m3` by tiše rozbila hledání
   (vektor dotazu se porovnává s vektory v DB), jiná gemma by dávala podle
   stroje jiné výsledky.
3. Nic dalšího: aplikace si ho do 15 s najde, nahraje modely a začne na něj
   posílat dotazy. Ověření: `GET /api/stav`, nebo
   `uv run python benchmarky/soubeh/bench_soubeh.py`.

`OLLAMA_NUM_PARALLEL` (souběh uvnitř jednoho stroje) je nastavení serveru
Ollamy, ne aplikace. Jestli na Sparku něco přidá, se musí změřit – násobí
paměť na kontext u všech modelů. Až bude nastavené, zvednout
`OLLAMA_SOUBEZNE` (výchozí 1 = další dotaz jde hned na další stroj).

---

## Když hledání „nic nedělá"

Ollama model po ~5 minutách nečinnosti **odloží z paměti**. Další dotaz
ho musí načíst znovu – router `gemma4:26b` má 19 GB a načtení trvá kolem
10 sekund; `ollama ps` mezitím neukazuje nic a aplikace vypadá zaseknutě.

Klient proto posílá `keep_alive: "2h"` s každým požadavkem
(`ollama_client.KEEP_ALIVE`) a API i CLI model při startu předehřívají
(`priprav_modely()`). Když se model přesto načítá, CLI to vypíše:

    POZN: model se musel načíst z disku (10.2 s). Další dotaz už bude rychlý.

S načteným modelem trvá dotaz **2–3 s** (router je ~1,5 s z toho).

Kontrola, co je právě v paměti:

    curl http://10.6.38.10:11434/api/ps

POZOR: `ollama ps` spuštěné lokálně se ptá `localhost`, kde nic neběží –
musí se mířit na DGX. Přehled za všechny stroje dá `GET /api/stav`.

---

## OpenAI

**Klíč je v `key.yaml` v kořeni projektu** (v `.gitignore`) a do tohohle souboru nepatří.
Načítá se přes `common.config.nacti_openai_klic()`.

Pozor: `key.yaml` **není validní YAML mapa** — chybí mezera za dvojtečkou
(`key:sk-proj-...`), takže `yaml.safe_load()[...]` na něm spadne. Proto
ta funkce parsuje soubor ručně.

Když soubor chybí, má špatný tvar nebo klíč OpenAI odmítne, skončí
`extrakce_3_json.py --beh` hned chybou `CHYBA KLICE OPENAI` (kód 2).

**POZOR NA PENÍZE:** na účtu jsou jednotky dolarů. Používat **výhradně
`gpt-6-luna`** (`config.OPENAI_MODEL`) a vždy s `reasoning_effort="none"`.
`gpt-4o`, `gpt-4o-mini` ani řadu `sol` nepouštět. Rozpočtový strop běhu
je `config.CLOUD_STROP_USD`.

---

## Když pgAdmin nenaběhne

Skoro vždy je to chybějící `pgpass`. Je v `.gitignore`, takže po
naklonování repozitáře chybí — a Docker si na místě chybějícího
bind-mountu vyrobí **adresář**, což pgAdmin shodí bez srozumitelné chyby.

Řešení:

    uv run python provoz_priprava.py

Skript adresáře smaže, `pgpass` založí a zkontroluje i ostatní
bind-mounty (`pgadmin-servers.json`, `init-db.sql`).

## Když chybí tabulky

`init-db.sql` se spouští **jen na prázdném volume**. Po změně DDL:

    docker compose down -v && docker compose up -d

Bez přepínače `-v` se volume zachová, init skript se nespustí a vypadá
to jako chyba ve skriptu.
