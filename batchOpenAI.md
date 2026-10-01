# OpenAI Batch API – routy, zprávy, stavy

Referenční popis API, které používá `extrahuj_json_cloud.py`. Po vzoru
Swaggeru: routa → co posílám → co se vrací. Příklady jsou **skutečné**
z testovacího běhu 29. 9. 2026 (`data/spc/_extrakce_test/`), dlouhé
texty zkrácené (`…`). Kde příklad není z našeho běhu, ale z dokumentace
OpenAI, je to označené.

Základ URL: `https://api.openai.com`
Autorizace u všech rout: hlavička `Authorization: Bearer sk-proj-…`
(klíč z `legacy/key.yaml`, `config.nacti_openai_klic()`).

## Tok jedné dávky

```
 1. POST /v1/files                 nahrát JSONL (purpose=batch)       → file_id
 2. POST /v1/batches               založit dávku nad file_id          → batch_id
 3. GET  /v1/batches/{batch_id}    ptát se na stav (runner à 60 s)    → status, request_counts
      validating → in_progress → finalizing → completed
                 ↘ failed (validace)         ↘ expired (nestihlo se za 24 h)
 4. GET  /v1/files/{file_id}/content   stáhnout output_file_id + error_file_id
 5. párovat řádky podle custom_id (POŘADÍ NENÍ ZARUČENÉ)

 jen v nouzi:
    POST /v1/batches/{batch_id}/cancel    zrušit dávku
    GET  /v1/batches?limit=100            seznam dávek (srovnání se sirotky)
```

| routa | funkce v `extrahuj_json_cloud.py` |
|---|---|
| `POST /v1/files` | `odesli_davky()` → `api.files.create(...)` |
| `POST /v1/batches` | `odesli_davky()` → `api.batches.create(...)` |
| `GET /v1/batches/{id}` | `sleduj()` → `api.batches.retrieve(...)` |
| `GET /v1/files/{id}/content` | `stahni()` → `api.files.content(...)` |
| `GET /v1/batches` | `srovnej_s_openai()` → `api.batches.list(...)` |
| `POST /v1/batches/{id}/cancel` | ručně (zatím ne v runneru) |

---

## Co je JSONL

Vstup i výstup Batch API je **JSONL („JSON Lines")**: textový soubor,
kde **každý řádek je samostatný, úplný JSON objekt**. Nemá kořenový
objekt ani pole: žádné `[` `]` kolem, žádné čárky mezi řádky.

```
{"custom_id": "cz_15430|indikace|p1", "method": "POST", "url": "/v1/chat/completions", "body": {...}}
{"custom_id": "cz_15430|davkovani|p1", "method": "POST", "url": "/v1/chat/completions", "body": {...}}
{"custom_id": "cz_60595|indikace|p1", "method": "POST", "url": "/v1/chat/completions", "body": {...}}
```

| běžný JSON | JSONL |
|---|---|
| `[ {…}, {…}, {…} ]`, jeden celek | `{…}` ⏎ `{…}` ⏎ `{…}`, co řádek, to objekt |
| aby se dal přečíst, musí se načíst celý | čte se řádek po řádku, i 200 MB soubor |
| chyba kdekoli rozbije celý soubor | chyba je na konkrétním řádku (odtud `"line": 1` v chybě dávky) |

V příkladech níže je jeden řádek kvůli čitelnosti rozepsaný na víc řádků.
**V souboru je vždy celý na jednom řádku.**

---

## 1. `POST /v1/files` – nahrání vstupního souboru

Posílá se **soubor**, ne JSON objekt, jako příloha formuláře
(`multipart/form-data`), stejně jako upload souboru na webu.

**Request:** `multipart/form-data`

| pole | hodnota |
|---|---|
| `purpose` | `batch` |
| `file` | `davka_0002.jsonl` – JSONL, **jeden řádek = jeden požadavek** |

Limity: max. 50 000 požadavků a 200 MB na soubor. Runner posílá 1 000
požadavků na dávku (`--velikost-davky`).

### Jeden řádek JSONL (= jeden objekt, jeden požadavek)

Každý řádek nese **celý vlastní prompt**. Společný prompt pro dávku
Batch API nezná. `body` je přesně totéž tělo jako u běžného
`POST /v1/chat/completions` (`common/extrakce.py: telo_cloud()`).

```json
{
  "custom_id": "cz_15430|indikace|p1",
  "method": "POST",
  "url": "/v1/chat/completions",
  "body": {
    "model": "gpt-6-luna",
    "messages": [
      {
        "role": "system",
        "content": "Jsi asistent pro strukturovanou extrakci informací z farmaceutických SPC dokumentů. …"
      },
      {
        "role": "user",
        "content": "Z textu sekce indikace vytvoř JSON: {\"indikace\": [{...}]}. …\n\n--- TEXT SEKCE ---\n…ořezaný text sekce 4.1…\n--- KONEC ---"
      }
    ],
    "response_format": { "type": "json_object" },
    "reasoning_effort": "none",
    "temperature": 0,
    "seed": 42
  }
}
```

| pole | význam |
|---|---|
| `custom_id` | **náš klíč pro párování**: `<složka SPC>\|<sekce>\|p<pokus>`. Unikátní v rámci souboru. Pokus odliší opakování téhož požadavku |
| `method`, `url` | vždy `POST` a `/v1/chat/completions` – musí sedět s `endpoint` dávky |
| `body.model` | jen `gpt-6-luna` (`config.OPENAI_MODEL`) |
| `body.messages` | system (`SYSTEM_PROMPT`) + user (`PROMPTY[sekce]` + text). **Když chybí, OpenAI shodí CELOU dávku** (viz kap. 3) |
| `body.response_format` | JSON mód – odpověď je validní JSON |
| `body.reasoning_effort` | `none` – bez placených reasoning tokenů (luna nebere `minimal`) |
| `body.temperature`, `body.seed` | 0 a 42 – co nejopakovatelnější výstup |

**Response** `200 OK`:

```json
{
  "id": "file-WSWT79PMeoPcEJ3trFKmpQ",
  "object": "file",
  "purpose": "batch",
  "filename": "davka_0002.jsonl",
  "bytes": 123456,
  "created_at": 1790705880,
  "status": "processed"
}
```

(tvar podle dokumentace; `id` je skutečné z dávky 2)

---

## 2. `POST /v1/batches` – založení dávky

**Request:** `application/json`

```json
{
  "input_file_id": "file-WSWT79PMeoPcEJ3trFKmpQ",
  "endpoint": "/v1/chat/completions",
  "completion_window": "24h",
  "metadata": { "davka": "2", "beh": "test" }
}
```

| pole | význam |
|---|---|
| `input_file_id` | `id` z kroku 1 |
| `endpoint` | musí sedět s `url` v řádcích |
| `completion_window` | jediná povolená hodnota `24h` |
| `metadata` | naše značky: číslo dávky z `stav.sqlite` a druh běhu (`korpus` / `test`). Podle nich `srovnej_s_openai()` najde dávku, o které DB neví |

**Response** `200 OK`: objekt dávky (tvar viz kap. 3) se `status: "validating"`.

⚠ **Neexistující `input_file_id` routa NEODMÍTNE.** Dávka se založí
a selže až při validaci (`failed`, v testu po 15 minutách):
`invalid_request: Cannot find file file-…`.

---

## 3. `GET /v1/batches/{batch_id}` – stav dávky

Runner se ptá každých 60 s (`--interval`). Do logu zapíše jen změnu.

**Response** `200 OK` – dávka hotová (skutečná, dávka 2):

```json
{
  "id": "batch_6abc00d919e081908a2139a6f0445973",
  "object": "batch",
  "endpoint": "/v1/chat/completions",
  "model": "gpt-6-luna",
  "input_file_id": "file-WSWT79PMeoPcEJ3trFKmpQ",
  "completion_window": "24h",
  "status": "completed",
  "output_file_id": "file-V7XpECC2hkGU5DSKJpNEDr",
  "error_file_id": null,
  "errors": null,
  "created_at": 1790705881,
  "in_progress_at": 1790705882,
  "finalizing_at": 1790706017,
  "completed_at": 1790706019,
  "expires_at": 1790792281,
  "failed_at": null,
  "expired_at": null,
  "cancelling_at": null,
  "cancelled_at": null,
  "request_counts": { "completed": 19, "failed": 0, "total": 19 },
  "metadata": { "davka": "2", "beh": "test" },
  "usage": {
    "input_tokens": 25214,
    "input_tokens_details": { "cached_tokens": 0 },
    "output_tokens": 12974,
    "output_tokens_details": { "reasoning_tokens": 0 },
    "total_tokens": 38188
  }
}
```

**Response** `200 OK` – dávka neprošla validací (skutečná, dávka 1 testu
„požadavek bez promptu"):

```json
{
  "id": "batch_6abc00afd0748190b3fefb477db8e5c5",
  "status": "failed",
  "output_file_id": null,
  "error_file_id": null,
  "errors": {
    "object": "list",
    "data": [
      {
        "code": "missing_required_parameter",
        "line": 1,
        "message": "Missing required parameter: 'messages'.",
        "param": "body.messages"
      }
    ]
  },
  "failed_at": 1790705840,
  "request_counts": { "completed": 0, "failed": 0, "total": 0 },
  "metadata": { "davka": "1", "beh": "test" }
}
```

`errors.data[].line` je **číslo řádku JSONL (od 1)**. Runner podle něj
najde `custom_id` v lokálním `davka_NNNN.jsonl`, ten jeden požadavek
označí jako `chyba` a ostatní vrátí do fronty.

### Stavy dávky (`status`)

| status | význam | co dělá runner |
|---|---|---|
| `validating` | kontrola souboru (20 s až 15 min) | čeká |
| `in_progress` | běží; `request_counts.completed` roste | čeká, loguje průběh |
| `finalizing` | skládá výstupní soubory | čeká |
| `completed` | hotovo, `output_file_id` (+ případně `error_file_id`) | stáhne a zpracuje |
| `failed` | neprošla validace, **nic se nezpracovalo, nic se neplatí** | vadné řádky → `chyba`, zdravé → fronta; bez čísla řádku → vše `chyba`; limit fronty → vše zpět do fronty |
| `expired` | nestihlo se za 24 h; hotová část v `output_file_id` | stáhne hotové, zbytek → `chyba` (`--znovu-chybne`) |
| `cancelling` / `cancelled` | zrušeno ručně; hotová část se platí | zbytek → `chyba` |

`request_counts`: `total` = počet řádků, `completed` = úspěšně
odpovězené (HTTP 200), `failed` = řádky s chybou.

---

## 4. `GET /v1/files/{file_id}/content` – výsledky

Vrací JSONL. Runner stáhne oba soubory, uloží je jako auditní kopii
(`davka_NNNN.out.jsonl`, `davka_NNNN.err.jsonl`) a každý řádek zpracuje
funkcí `zpracuj_radek()` → `common/extrakce.py: zpracuj_odpoved()`
(stejné zpracování jako u sync extrakce).

### Řádek `output_file_id` – úspěch (skutečný, dávka 2)

```json
{
  "id": "batch_req_6abc0161bfb08190b575e5615b7b273d",
  "custom_id": "cz_15430|indikace|p1",
  "response": {
    "status_code": 200,
    "request_id": "5f0fcb70-15df-4036-92bf-e465514e4eef",
    "body": {
      "id": "chatcmpl-ETWhoqAOh9FDeMnni1RqXOrcLy9mE",
      "object": "chat.completion",
      "model": "gpt-6-luna",
      "choices": [
        {
          "index": 0,
          "message": {
            "role": "assistant",
            "content": "{\"indikace\":[{\"doslovne\":\"Charakterizace solitárního plicního nodu (uzlu)\",\"laicky\":\"určení povahy osamoceného plicního uzlu\",\"klic\":\"solitární plicní uzel\"}, …]}",
            "refusal": null
          },
          "finish_reason": "stop"
        }
      ],
      "usage": {
        "prompt_tokens": 2256,
        "completion_tokens": 2179,
        "total_tokens": 4435,
        "prompt_tokens_details": { "cached_tokens": 0 },
        "completion_tokens_details": { "reasoning_tokens": 0 }
      }
    }
  },
  "error": null
}
```

| pole | co z něj runner bere |
|---|---|
| `custom_id` | párování → řádek `pozadavky` v `stav.sqlite` |
| `response.status_code` | 200 = úspěch, jinak `chyba` |
| `response.body.choices[0].message.content` | JSON s položkami → `zpracuj_odpoved()` → `json/<sekce>.json` |
| `response.body.usage` | `prompt_tokens`, `completion_tokens` → skutečná cena (Batch = poloviční) |
| `finish_reason` | `stop` = celý výstup; `length` by znamenal useknutý JSON → skončí jako `selhala_extrakce` |

### Řádek `error_file_id` – chyba jednoho požadavku

Tvar podle dokumentace OpenAI (v našem testu nenastal):

```json
{
  "id": "batch_req_…",
  "custom_id": "cz_12345|nezadouci_ucinky|p1",
  "response": {
    "status_code": 400,
    "request_id": "…",
    "body": {
      "error": {
        "message": "…",
        "type": "invalid_request_error",
        "param": "…",
        "code": "…"
      }
    }
  },
  "error": null
}
```

Požadavek, který nestihl 24 h (`expired`):

```json
{
  "id": "batch_req_…",
  "custom_id": "cz_12345|davkovani|p1",
  "response": null,
  "error": { "code": "batch_expired", "message": "This request could not be executed before the completion window expired." }
}
```

Runner v obou případech: `pozadavky.stav = 'chyba'` + text chyby →
`report.md` → `--znovu-chybne`.

---

## 5. `POST /v1/batches/{batch_id}/cancel` – zrušení

Bez těla. Vrací objekt dávky se `status: "cancelling"`, později
`cancelled`. **Hotové požadavky se zaplatí**, zbytek ne. Použito 29. 9.
na sirotčí testovací dávku (0 hotových = 0 $).

## 6. `GET /v1/batches?limit=100` – seznam dávek

Vrací `{"object": "list", "data": [ …objekty dávek… ], "has_more": …}`,
nejnovější první. Runner ho při každém startu projde
(`srovnej_s_openai()`) a převezme dávky s `metadata.beh` = tento běh,
o kterých `stav.sqlite` neví (pád mezi kroky 2 a zápisem do DB).

---

## Cena – metrika ze skutečného běhu (1. 10. 2026)

gpt-6-luna Batch: vstup **0,05 $**, výstup **0,25 $** za 1 M tokenů
(sync 0,10 / 0,50). Výstup = 78 % ceny. Podrobně v `poznatky.md` 1. 10.

| | |
|---|---|
| 1 M výstupních tokenů | **~236 kompletních SPC**, ~18 700 položek, ~0,32 $ i se vstupem |
| 1 SPC (4 sekce) | 5 968 vstup + 4 243 výstup tokenů = **0,00136 $** |
| 1 000 SPC | **~1,36 $** |
| celý korpus 5 880 SPC | **~8,0 $** (zaplaceno 10,18 $ i s opakováním a smyčkami) |
| za 1 $ | ~735 SPC |

---

## Co je dobré vědět

- **Pořadí řádků ve výstupu neodpovídá vstupu.** Vždy párovat podle `custom_id`.
- **Jeden vadný řádek shodí validaci celé dávky.** Runner proto těla
  kontroluje lokálně před odesláním (`lokalni_vada()`).
- **Cena:** Batch = 50 % ceny sync. Počítá se jen z úspěšných požadavků
  (`usage`). Dávka `failed` při validaci nestojí nic.
- **Útrata ani zůstatek přes tenhle klíč zjistit nejdou.** Runner si útratu
  počítá sám z `usage` (`stav.sqlite`, sloupec `cena_usd`). Zůstatek je jen
  na platform.openai.com → Settings → Billing.
- **Soubory u OpenAI zůstávají** (vstup i výstup). Časem je jde smazat
  `DELETE /v1/files/{id}`. Lokální kopie jsou v `data/spc/_extrakce/davky/`.
