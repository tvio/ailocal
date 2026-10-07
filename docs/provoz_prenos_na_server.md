# Přenos na testovací server (Windows → RHEL 9.4, x86)

Postup z 7. 10. 2026. **Zatím neprovedeno – psáno z notebooku, na Linuxu
nic z toho neběželo.** Co se při přenosu ukáže jinak, zapsat do
`poznatky.md` a opravit tady.

Cíl: na serveru běží všechno (hledání i pipeline) a dál se tam vyvíjí přes
VS Code Remote-SSH. Notebook přestává být hlavní kopií dat.

| část | velikost | jak se přenáší |
|---|---|---|
| kód, dokumentace, `CLAUDE.md` | malé | `git clone` (hlavní větev `master`; `v1.5` do ní byla sloučena 7. 10.) |
| `data/spc`, `data/detaily_leciv`, seznamy | 4,7 GB, statisíce souborů | `tar` proudem přes ssh |
| databáze (hlavně `leciva_search` s vektory) | 6,3 GB | `pg_dump -Fc` → `pg_restore` |
| `key.yaml` (OpenAI) | – | ručně, není v gitu |
| nastavení adres | – | `.env` podle `.env.example` |

`data/leky` (rejstřík) se nepřenáší – na Windows jsou to junctions; na
serveru ho postaví krok 6 pipeline jako symlinky.

---

## 0. Co musí být na serveru

- `git`, **Docker s `docker compose`** (RHEL má výchozí podman – buď
  nainstalovat docker-ce, nebo `podman-docker` + `podman-compose`; s podmanem
  nezkoušeno), `uv` (Python 3.13 si stáhne sám).
- Dosah na síť – ověřit předem:

```bash
curl -s http://10.6.38.10:11434/api/version      # Ollama na Sparku (hledání)
curl -s http://10.6.38.10:5001/version           # Docling Serve (krok 1 pipeline) – na notebooku šel jen tunelem!
curl -sI https://api.openai.com | head -1        # extrakce (krok 3)
curl -sI https://prehledy.sukl.gov.cz | head -1  # seznam léčiv a SPC (krok 1)
curl -sI https://www.ema.europa.eu | head -1     # EU dokumenty (krok 1)
```

- Místo na disku: ~5 GB data + ~7 GB databáze + ~4 GB dump dočasně +
  několik GB závislostí (`docling` táhne torch).

## 1. Kód

```bash
cd ~ && git clone https://github.com/tvio/ailocal.git && cd ailocal    # hlavní větev master
uv sync
```

Cestu si zapamatuj – podle ní se jmenuje složka Claude Code (kap. 8).

## 2. Nastavení

```bash
cp .env.example .env            # upravit adresy; .env je v .gitignore
echo 'export UV_ENV_FILE=.env' >> ~/.bashrc && source ~/.bashrc   # uv run ho pak načítá samo
uv run python provoz_priprava.py   # pgpass a další soubory pro Docker
```

`key.yaml` z notebooku (PowerShell):

```powershell
scp C:\python\ailocal\key.yaml uzivatel@server:~/ailocal/key.yaml
```

Na serveru `chmod 600 key.yaml`. Běh extrakce klíč před startem ověří.

## 3. Data korpusu

Z notebooku (PowerShell; Windows má `tar` i `ssh`). Proudem, ne `scp -r` –
jsou to statisíce malých souborů:

```powershell
cd C:\python\ailocal
tar -cf - data/spc data/detaily_leciv data/pool_leciv.json data/pool_leciv.meta.json data/hrazene_scau.json data/ciselnik_latky.json | ssh uzivatel@server "tar -xf - -C ~/ailocal"
```

Přenese se i stav konverze (`data/spc/_stav.sqlite`) a extrakce
(`data/spc/_extrakce/stav.sqlite`), takže pipeline na serveru naváže a nic
nepočítá ani neplatí znovu. Kontrola na serveru:

```bash
uv run python extrakce_all.py --stav     # konverze 5 897 ok, sekce 5 880, extrakce 23 495 hotovo
```

## 4. Databáze

**Na serveru** – nejdřív prázdná databáze z vlastního image (pgvector +
český slovník hunspell):

```bash
docker compose build && docker compose up -d
docker exec localsemantic-postgres psql -U localsemantic -d localsemantic -Atc "select to_tsvector('czech_unaccent','pálení žáhy')"
# musí vrátit 'pálení':1 'žáha':2  – tedy „žáhy" převedené na „žáha"
```

Tahle kontrola je důležitá: kontejner na notebooku běží ze základního image
`pgvector/pgvector:pg17` a vlastní image z `Dockerfile.postgres` se na
serveru sestaví a použije poprvé. Bez slovníku by obnova spadla nebo by
fulltext přestal skloňovat.

Na RHEL může SELinux zakázat kontejneru číst připojené soubory
(`init-db.sql`, `pgpass`). Když kontejner hlásí „permission denied",
přidat k těm řádkům v `docker-compose.yml` `:z` (`…:ro,z`).

**Na notebooku** – dump (PowerShell). Ne přes `>`: PowerShell binární
výstup poškodí.

```powershell
docker exec localsemantic-postgres pg_dump -U localsemantic -d localsemantic -Fc -f /tmp/localsemantic.dump
docker cp localsemantic-postgres:/tmp/localsemantic.dump C:\python\ailocal\data\localsemantic.dump
docker exec localsemantic-postgres rm /tmp/localsemantic.dump
scp C:\python\ailocal\data\localsemantic.dump uzivatel@server:~/ailocal/data/
```

**Na serveru** – obnova:

```bash
docker cp data/localsemantic.dump localsemantic-postgres:/tmp/
docker exec localsemantic-postgres pg_restore -U localsemantic -d localsemantic --clean --if-exists --no-owner -j 4 /tmp/localsemantic.dump
docker exec localsemantic-postgres rm /tmp/localsemantic.dump
```

Vektory jsou v dumpu, embeddingy se **nepočítají znovu** (ušetří ~2 h
a Ollamu). Znovu se staví indexy a fulltextový sloupec. Kontrola:

```bash
uv run python extrakce_all.py --stav     # db: kodu 8778, SPC 5880, hledacich radku 472844; bez vektoru 0
docker exec localsemantic-postgres psql -U localsemantic -d localsemantic -Atc "select count(*) from slovnik_dotazu"
```

Hledací slovník (tabulka `slovnik_dotazu`) jde v dumpu s sebou.

## 5. Spuštění a ověření

```bash
uv run python hledani_cli.py "mám reflux"                    # RENNIE, GAPULSID…
uv run python hledani_evaluace.py                            # čekáno 18/20, 69 %, 5/6
uv run python benchmarky/soubeh/bench_soubeh.py --simulace   # rozdělování zátěže, bez Ollamy
uv run python extrakce_6_rejstrik.py                         # rejstřík jako symlinky
uv run uvicorn api:app --host 0.0.0.0 --port 8000            # GUI pro ostatní v síti
```

Port pro GUI: `sudo firewall-cmd --add-port=8000/tcp --permanent && sudo
firewall-cmd --reload`. `GET /api/stav` ukáže i stav strojů s Ollamou.

Evaluace je kontrola, že přenos nic nezměnil: jiná čísla = jiná data,
jiný model, nebo nefunkční fulltext.

## 6. Co na Linuxu nepoběží nebo je jinak

| věc | stav |
|---|---|
| **SPC ve formátu `.doc`** (krok 1) | převádí se přes MS Word a PowerShell (`common/doc_na_pdf.ps1`) – **na Linuxu nefunguje**. Týká se 4 dokumentů z 5 880; už převedené se přenesou s daty. Nové nebo změněné `.doc` potřebují náhradu přes LibreOffice (`todo.md`). |
| Docling Serve | na notebooku přes SSH tunel na `localhost:5001`; na serveru adresa v `.env` (`DOCLING_SERVE_URL`) – ověřit, že je port ze serveru dostupný |
| zámky proti souběžnému běhu | kód má větev pro Linux (`fcntl`), nezkoušeno |
| rejstřík `data/leky` | symlinky místo junctions, nezkoušeno |
| velikost písmen v názvech souborů | Linux ji rozlišuje, Windows ne – nezkoušeno |
| konce řádků | git na Linuxu dá LF, kód na ně nespoléhá |

## 7. Služba a měsíční běh (až bude ruční běh ověřený)

- API jako služba systemd (`ExecStart=… uv run uvicorn api:app --host
  0.0.0.0 --port 8000`, `EnvironmentFile=…/.env`, `WorkingDirectory`).
- Pipeline: `extrakce_all.py --vse` z cronu jednou měsíčně. Má zámek, log
  a návratové kódy (`docs/pipeline_prehled.md`). **Pozor:** krok 4 plní
  databázi od nuly (~40 min) a krok 3 stojí peníze – rozpočtový strop je
  `config.CLOUD_STROP_USD`. Před prvním ostrým `--vse` pustit kroky zvlášť.

## 8. Claude Code na serveru

**Co se přenese samo gitem:** `CLAUDE.md` (pravidla a mapa projektu),
`poznatky.md`, `aktualnistav.md`, `todo.md`, `docs/` a `.claude/settings.json`.
To je všechno, z čeho Claude o projektu ví – na serveru to načte stejně.

**Paměť Claude je k 7. 10. prázdná.** Složka
`C:\Users\hajek\.claude\projects\c--python-ailocal\memory\` neobsahuje
žádný záznam; trvalé věci jsou v `CLAUDE.md`. Co má Claude vědět i na
serveru, patří proto do `CLAUDE.md`, ne do paměti jednoho počítače.

Paměť i historie konverzací jsou uložené **podle cesty k projektu** na
daném stroji. Na serveru pro `~/ailocal` uživatele `uzivatel` je to
`~/.claude/projects/-home-uzivatel-ailocal/` (cesta s pomlčkami místo
lomítek; vznikne při prvním spuštění Claude Code v té složce). Kdyby
v paměti časem něco bylo:

```powershell
scp -r C:\Users\hajek\.claude\projects\c--python-ailocal\memory uzivatel@server:~/.claude/projects/-home-uzivatel-ailocal/
```

- **Historie konverzací** (`*.jsonl` v téže složce, 26 MB) jde zkopírovat
  stejně, ale obsahuje cesty z Windows – jestli na ni půjde na serveru
  navázat, není ověřeno. Bezpečnější je začít novou konverzaci; stav je
  v `aktualnistav.md`.
- **Osobní nastavení** (`~/.claude/settings.json`, `~/.claude/skills/`) se
  dá zkopírovat. **`.credentials.json` nekopírovat** – na serveru se
  přihlásit znovu.
- `.claude/settings.local.json` v projektu má povolené příkazy psané pro
  Windows (cesty `C:\…`); na serveru se povolení nasbírají znovu.

## 9. Po přenosu

- **Hlavní kopie dat a databáze je server.** Na notebooku už pipeline
  nepouštět, jinak se stavy rozejdou.
- Kód se dál sdílí gitem. Při práci přes Remote-SSH se commituje na
  serveru; notebook si změny stáhne `git pull`.
- Vývoj z notebooku proti datům serveru: v `.env` na notebooku nastavit
  `PG_HOST` na server (port 5432 musí být otevřený) – druhá kopie
  databáze pak není potřeba.
