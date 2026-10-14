# Changelog

Hotové nové funkce a opravy, **nejnovější nahoře**. Jeden řádek na
změnu; rozbor a čísla patří do `poznatky.md`, rozpracovaná práce do
`aktualnistav.md`. Starší historie je v `git log`.

Značky: **Nové** · **Oprava** · **Změna** · **Provoz** · **Dokumentace**

## 2026-10-14
- **Nové:** GUI – blok „Jak hledat – příklady": 31 ověřených dotazů po
  kategoriích (laik, výdej a hrazení, látka/síla/kód, celá sekce, NÚ,
  věk slovem i číslem, název začíná/končí/obsahuje/přibližně, nic);
  klik vloží dotaz a rovnou hledá (`static/app.js` `PRIKLADY`).
- **Změna:** GUI – odebrány posuvníky „Práh podobnosti" a „Zvýraznit od";
  GUI posílá vždy práh 0,60. Omezení na sekci zůstalo ve vlastním bloku.
- **Provoz:** `.claude/settings.json` – čtení, `uv run`, git ke čtení
  a úpravy souborů projektu bez ptaní; zápis přes Docker, `systemctl`,
  `sudo`, `dnf`, `firewall-cmd` a drahé kroky pipeline vždy se schválením
  (`ask`). `settings.local.json` je osobní pro stroj – vyřazený z gitu
  a v `.gitignore`.
- **Změna:** léky s přesnou shodou (cosine 1,000) jsou ve výsledcích
  nahoře abecedně, ostatní pod nimi podle shody (cosine, číslo v GUI), ne
  podle RRF – dřív 0,838 pod 0,792; záhlaví v GUI říká kolik přesných
  (`common/hledani.py` `seskup`, `SHODA_PRESNA`; API pole `presnych`).
  Čtení sekce zůstává v pořadí dokumentu.
- **Změna:** výběr jen přesným filtrem (látka, název, kód, síla, ATC) je
  abecedně a úplný – dřív strop 50 léků („paracetamol" 50 → 67).
- **Oprava:** hledání v API vracelo max. 50 léků (výchozí `leciv`), teď
  200 – „mám rýmu" 50 → 177 léků.
- **Oprava:** `odstup` v API se počítá vůči nejvyššímu skóre, ne vůči
  prvnímu řádku.
- **Oprava:** stránkování výsledků hledání už znovu nehledá – výsledek se
  drží 10 min v paměti API, další stránka ~2 ms místo ~5 s a je ze
  stejného hledání jako první (`api.py`, `_CacheHledani`).
- **Dokumentace:** `todo.md` přepsaný proti kódu – hotové úkoly pryč,
  u otevřených odkaz na soubor a řádek.
- **Dokumentace:** `CLAUDE.md` – na serveru bez schválení jen čtení;
  zavedený tenhle changelog.

## 2026-10-09
- **Provoz:** aplikace nasazená na server – DB obnovená z dumpu do
  `data/pgdata` (`PGDATA_DIR`), HTTPS přes kontejner nginx na portu 8090,
  API jako služba systemd `localsemantic-api` přes socket `run/api.sock`.
