# jak pustit

uv run python extrahuj_json_cloud.py --beh --max-davek 1   # pilot: 1 dávka = 1 000 požadavků, ~0,3 $
uv run python extrahuj_json_cloud.py --beh                 # zbytek, naváže
uv run python extrahuj_json_cloud.py --stav                # kdykoli: souhrn + report.md

# bez davky jed sledovani
Kdybys chtěl opravdu jen dosledovat rozjeté a nic nového neposílat, přidej --max-davek 0.

Při znovuspuštění se tokeny nepočítají znovu, takže runner naváže během pár sekund.

# jak spusti znovu chyby
Chyby na konci najdeš v data/spc/_extrakce/report.md. Rozhodneš, co s nimi, a pak je jde poslat znovu přes --znovu-chybne.

# Kde je vidět, co prošlo a co ne:

1. Stav každého požadavku i dávky je v data/spc/_extrakce/stav.sqlite. Přežije pád, Ctrl+C i restart a stejný příkaz na něj naváže.
2. Log se píše průběžně na obrazovku i do data/spc/_extrakce/log/. Je v něm stav každé dávky (validace → zpracování 11/19 → hotovo) a každá chyba s ID.
3. Report data/spc/_extrakce/report.md obsahuje tabulku dávek a seznam všech chybných požadavků s důvodem.
4. Opakování: --znovu-chybne vrátí do fronty všechny chybné, --znovu-seznam soubor.txt jen vybrané ID. To je případ „54 vadných" po zapnutí kontrol.

# Jak běh spustit nezávisle na IDE

Proces spuštěný z VS Code zavřením IDE skončí. Dávky u OpenAI sice běží
dál, ale výsledky nikdo nestáhne. Proto:

## 1. Pilot – ručně v samostatném okně

```powershell
Start-Process powershell -ArgumentList '-NoExit','-Command','cd C:\python\ailocal; uv run python extrahuj_json_cloud.py --beh --max-davek 1'
```

`-NoExit` nechá okno otevřené i po konci (je vidět závěrečný souhrn).

## 2. Hlídač – Plánovač úloh každých 15 minut

Runner má **zámek** (`data/spc/_extrakce/beh.lock`): když už běží, další
spuštění se hned tiše ukončí. Když spadl, další spuštění naváže. Zámek
drží operační systém, takže po pádu nezůstane viset.

Během pilotu jen hlídat, nic nového neposílat (`--max-davek 0`):

```powershell
schtasks /Create /TN "localsemantic_extrakce" /SC MINUTE /MO 15 /TR "powershell -NoProfile -WindowStyle Hidden -Command \"cd C:\python\ailocal; uv run python extrahuj_json_cloud.py --beh --max-davek 0\""
```

Po pilotu přepnout na celý korpus (bez `--max-davek`):

```powershell
schtasks /Delete /TN "localsemantic_extrakce" /F
schtasks /Create /TN "localsemantic_extrakce" /SC MINUTE /MO 15 /TR "powershell -NoProfile -WindowStyle Hidden -Command \"cd C:\python\ailocal; uv run python extrahuj_json_cloud.py --beh\""
```

Po doběhnutí úlohu smazat: `schtasks /Delete /TN "localsemantic_extrakce" /F`

**Pozor:** `--max-davek N` platí pro JEDNO spuštění. Nechat ho v plánovači
s N > 0 znamená N nových dávek každých 15 minut.

## 3. Sledování odkudkoli

```powershell
# log naživo (nejnovější soubor)
Get-Content (Get-ChildItem C:\python\ailocal\data\spc\_extrakce\log\*.log | Sort-Object LastWriteTime | Select-Object -Last 1) -Wait -Tail 20

# souhrn + aktualizace report.md (jde i když běh právě jede)
uv run python extrahuj_json_cloud.py --stav
```

Uspání notebooku proces pozastaví, dávky u OpenAI běží dál a po probuzení
se stav dotáhne.
