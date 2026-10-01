# Na řadě (todo.md „TOP – úterý 29. 9.", tedy dnes; pořadí je závazné)
1. Detailně zmapovat, jak dnes funguje extrakce, a nic přitom neměnit. Jde o extrahuj_json.py, common/extrakce.py, orizni_na_jadro() a navazující kroky. Extrakce dnes čte jen data/leciva/ (32 léčiv) a běží na lokálním qwenu.
2. Napsat kontroly klíče a laického tvaru. U klíče: 1–4 slova, 1. pád, diakritika, opora ve zdroji, nesmí být obecný. U laického tvaru: opora ve zdroji nebo ve slovníku pojmů, případně kontrola gemmou. K tomu regresní sada známých zmetků (ULTRACOD „alenzie", OMEPRAZOL „řinčení", BISACODYL „ve třasu", HIDRASEC „onemocnění").
3. Spočítat cenu v cloudu na skutečném korpusu (5 880 SPC, tiktoken na *_orez.md). Dál změřit lunu na extrakci 4.8, tedy na vazbě účinek → frekvence, protože zatím byla měřená jen na zjednodušení. A přeměřit benchmark s promptem s diakritikou.
4. Teprve pak spustit extrahuj_json.py --korpus přes Batch API, se stavem po dokumentu a navazováním po pádu. Nový krok zapsat do pipeline.py a skripty.md.
Tvůj odhad tedy sedí: cloud čeká na úpravu extrakce a na kontroly zjednodušení.

# Rozpracované vedle toho
1. Úklid pipeline: pipeline.py o konvertuj_serve.py neví. Data leží ve dvou úložištích (data/leciva/ a data/spc/). naplni_db.py čte ze starého úložiště. Benchmarky pořád leží v kořeni projektu místo v benchmarky/.
2. Kontrola konverze nemá regresní sadu. Oprava jedné falešné chyby už jednou rozbila jiný dokument: PARALEN spadl z 93 % na 14 %.
3. Zbývá rozhodnout o 25 homeopatikách se SPC a o přípravcích bez SPC, které se mají ukazovat jen s atributy.
4. Tvoje ruční poznámky nahoře v todo.md: debug log do GUI, logování od A do Z, rozšíření výsledků o ATC skupinu a „proč lék na kašel vrací ACIFEIN".