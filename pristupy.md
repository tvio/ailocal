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
| `extrakce_stav` | co se povedlo a co ne (viz `stavy.md`) |
| `slovnik_pojmu` | odborný termín → laický tvar |
| `beh_log` | detailní log běhů jednotlivých kroků |

---

## Ollama

Klient zkouší v tomhle pořadí a bere první, která odpoví
(`common/ollama_client.KANDIDATI`):

1. `http://10.6.38.10:11434` — DGX Spark
2. `http://127.0.0.1:11434` — lokální

Bez autentizace. Modely: `qwen3.5:122b` (vše generativní),
`gemma4:31b` (kontrola), `bge-m3` (embedding).

---

## Když hledání „nic nedělá"

Ollama model po ~5 minutách nečinnosti **odloží z paměti**. Další dotaz
ho musí načíst znovu a qwen3.5:122b má **87,4 GB** – trvá to desítky
sekund až minuty, `ollama ps` mezitím neukazuje nic a skript vypadá
zaseknutě.

Klient proto posílá `keep_alive: "2h"` (`ollama_client.KEEP_ALIVE`).
Když se model přesto načítá, CLI to nově vypíše:

    POZN: model se musel načíst z disku (43.2 s). Další dotaz už bude rychlý.

S načteným modelem trvá celý dotaz **5–6 s**.

Kontrola, co je právě v paměti:

    curl http://10.6.38.10:11434/api/ps

POZOR: `ollama ps` spuštěné lokálně se ptá `localhost`, kde nic neběží –
musí se mířit na DGX.

---

## OpenAI

**Klíč je v `legacy/key.yaml`** a do tohohle souboru nepatří.
Načítá se přes `common.config.nacti_openai_klic()`.

Pozor: `key.yaml` **není validní YAML mapa** — chybí mezera za dvojtečkou
(`key:sk-proj-...`), takže `yaml.safe_load()[...]` na něm spadne. Proto
ta funkce parsuje soubor ručně.

**POZOR NA PENÍZE:** na účtu jsou jednotky dolarů. Používat **výhradně
`gpt-5-nano`** (`config.OPENAI_MODEL`). `gpt-4o` ani `gpt-4o-mini`
nepouštět — gpt-4o stojí násobně víc.

---

## Když pgAdmin nenaběhne

Skoro vždy je to chybějící `pgpass`. Je v `.gitignore`, takže po
naklonování repozitáře chybí — a Docker si na místě chybějícího
bind-mountu vyrobí **adresář**, což pgAdmin shodí bez srozumitelné chyby.

Řešení:

    uv run python priprav_infrastrukturu.py

Skript adresáře smaže, `pgpass` založí a zkontroluje i ostatní
bind-mounty (`pgadmin-servers.json`, `init-db.sql`).

## Když chybí tabulky

`init-db.sql` se spouští **jen na prázdném volume**. Po změně DDL:

    docker compose down -v && docker compose up -d

Bez přepínače `-v` se volume zachová, init skript se nespustí a vypadá
to jako chyba ve skriptu.
