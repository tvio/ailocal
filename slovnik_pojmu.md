# Číselník pojmů – odborný termín → laický tvar

Vzniká z extrakce nežádoucích účinků (`postav_slovnik.py`),
**není psaný ručně**. Slouží ke dvěma věcem:

1. **Sjednocení** – aby měl termín jeden tvar napříč aplikací.
   Bez toho měl každý pátý termín víc různých laických podob.
2. **Kontrola** – zjednodušení neověří ani doslovné porovnání
   se zdrojem (překlad tam doslova není), ani kontrola sekcí
   (té je řečeno, že zjednodušení se za chybu nepovažuje).

Sloupec **?** označuje dvojice, které kontrolní model označil
jako věcně nesedící – ty je potřeba projít okem.

- termínů celkem: **593**
- mělo víc laických tvarů: **1**
- označeno kontrolou: **31**
- ručně ověřeno člověkem: **67** (soubor `slovnik_rucni.json`, přebíjí generovaný tvar)

## K ručnímu projití

| ? | odborný termín | laický tvar | co vytkla kontrola |
|---|---|---|---|
| ⚠ | akutní renální selhání | náhlé přestat ledvinami, která přestane filtrovat odpad z krve | gramatická chyba ('přestat ledvinami') |
| ⚠ | akutní selhání jater | náhle nastalé přestat fungovat jater | gramaticky nesprávně/rozsypaná čeština |
| ⚠ | alkalické fosfatázy | Zvýšená hodnota alkalické fosfatázy v krvi | termín je název enzymu, laický tvar popisuje jeho zvýšenou hladinu |
| ⚠ | aseptická meningitida | zánět blan mozku způsobený lékem | aseptická meningitida nemusí být způsobena pouze lékem, ale i viry nebo jinými faktory |
| ⚠ | celulitida | rozlitého zánětu kůže | Gramaticky nesprávně (rozlitého zánětu kůže) |
| ⚠ | erythema nodosum | zánět krevních cév na nohou a jinde | Erythema nodosum je specificky bolestivý uzlový edém podkožního tkáně (především na lýtkách), nikoliv obecný zánět krevních cév. |
| ⚠ | folikulitida v místě aplikace | Zánět vlasového vlasu na miste aplikace | gramatická chyba 'Zánět vlasového vlasu' |
| ⚠ | hypersensitivita (včetně anafylaktické reakce a anafylaktického šoku) | přecitlivělost, včetně těžké alergické reakce a alergií šoku | překlep 'alergií šoku' místo 'alergického šoku' |
| ⚠ | krvácení z dásní | krvácení ze dvanácti | zaměna dásní za dvanáctník |
| ⚠ | lupus-like syndrom | příznaky připomínající lupénku (nebo systémový lupus) | Lupus-like syndrom připomíná systémový lupus, nikoliv lupénku (psoriázu), což jsou dvě zcela odlišná onemocnění. |
| ⚠ | metabolická acidóza s vysokou aniontovou mezerou | porucha kyselosti krve | příliš obecné, vynechává klíčovou informaci o aniontové meze |
| ⚠ | parestezie v místě aplikace | Ztráta citlivosti na miste aplikace | parestezie je brnění/mravenčení, nikoliv ztráta citlivosti (hypestezie/anestezie) |
| ⚠ | peptický vřed s krvácením | Rána na žaludeční sliznici nebo dvanáctníku, která začne krýt | překlep v textu 'začne krýt' místo 'krvácet' |
| ⚠ | periferní otok | nátoky na končetinách (ruce, nohy) | Slovo 'nátoky' není v tomto kontextu správný český termín pro edémy |
| ⚠ | poruchy vidění | Nechutné problémy se zrakem nebo rozostření | slovo 'Nechutné' je nesmyslné a nevhodné |
| ⚠ | poruchy vidění/miosa | problémy se zrakem nebo zvětšené zúžení zorničky | oxymoron 'zvětšené zúžení' |
| ⚠ | pálení žáhy a nauzea | Pálení žáhy a nevolnost | nauzea znamená nutnost jít na záchod/zvracení, nevolnost je subjektivní pocit |
| ⚠ | přechodná nebo trvalá ztráta sluchu | Časné nebo stálé oslepnutí na uši a nedostatek slyšení | nesrozumitelná formulace 'oslepnutí na uši' |
| ⚠ | renální insuficience manifestovaná primárně jako zvýšené hladiny sérového kreatininu a sérové urey | Selhání ledvin projevující se zvýšenými hodnotami jaterních látek v krvi | kreatinin a urea jsou ledvinové látky, nikoliv jaterní |
| ⚠ | rozmazané vidění(viz také bod 4.4.) | Mazani videni (viz take bod 4.4.) | nesrozumitelný text/chybí diakritika |
| ⚠ | selhání kostní dřeně | Nestárnutí kostní dřeně, která přestane tvořit krevní buňky | nesmyslné vyjádření 'nestárnutí kostní dřeně' |
| ⚠ | stupor | stāv (stav snižující vědomí) | Typografická chyba ('stāv') a nejasná formulace. |
| ⚠ | subakutní kožní lupus erythematodes (viz bod 4.4) | chronické onemocnění kůže podobné lupu, které reaguje na slunce | Nesprávné tvrzení 'podobné lupu' – jde o formu lupusu samotného. |
| ⚠ | suchost v místě aplikace | Souska na miste aplikace | Typografická chyba ('Souska'). |
| ⚠ | svědění v místě aplikace | Zapaleni na miste aplikace | svědění není totéž co zapalení |
| ⚠ | tendinopatie, někdy komplikovaná rupturou | choroba šlachy, která se občas zlomí | šlacha se neláme, ale trhá/rupturuje |
| ⚠ | vyrážka v místě aplikace | Vyprazdnění na miste aplikace | překlep 'Vyprazdnění' místo 'Vyrážka' |
| ⚠ | změny krevního obrazu | změny v krve | příliš obecné; změny v krvi mohou být i jiné než v krevním obrazu |
| ⚠ | zvracení (zejména na začátku léčby) | odtření žaludečního obsahu ústy | nesrozumitelná formulace/rozsypaná čeština |
| ⚠ | zvýšené jaterní enzymy | zvýšení hladiny enzymů v játrech | Zvýšené jaterní enzymy značí zvýšení jejich hladiny v krvi, nikoliv fyzické zvýšení množství enzymů přímo uvnitř játr. |
| ⚠ | zánětů žaludeční sliznice | léčba zánětu stěny žaludku | laický tvar přidává slovo 'léčba', což mění význam z diagnózy na proces léčení |

## Celý číselník

| odborný termín | laický tvar | výskytů | variant | ručně |
|---|---|---|---|---|
| abdominální bolest | bolest v břiše | 1 |  |  |
| abdominální bolest, nauzea, zvracení, dyspepsie, průjem | Bolí břicho, nevolnost, zvracení, špatné trávení, řídká stolice | 1 |  |  |
| abdominální diskomfort | nepříjemné pocity v břiše | 1 |  |  |
| abdominální distenze | nafouklé břicho | 1 |  |  |
| abnormality acidobazické rovnováhy | Narušení správného poměru kyselin a zásad v těle | 1 |  |  |
| abnormální chování | Podivné jednání | 1 |  |  |
| abnormální jaterní funkce se zvýšenou hladinou jaterních enzymů doprovázenou zvýšenou hladinou bilirubinu | porucha činnosti jater s vyššími hodnotami jaterních testů a bilirubinu | 1 |  |  |
| abnormální jaterní funkční testy | neobvyklé výsledky krevních testů na funkci jater | 1 |  |  |
| acne vulgaris | běžné akné | 1 |  | ✔ |
| agep (akutní generalizovaná exantematózní pustulóza) | Náhle vzniklá vyrážka s mnoha hnisavými puchýřky po celém těle | 1 |  |  |
| agitovanost | úzkostný neklid | 2 |  |  |
| agranulocytóza | vážný pokles bílých krvinek | 9 |  |  |
| agravace myastenie | zhoršení svalové slabosti při nemoci zvaná myastenie | 1 |  |  |
| agrese | agresivita | 1 |  |  |
| agresivita | agresivita | 2 |  |  |
| akné | Akne | 1 |  |  |
| akutní alergické stavy | náhlé alergické reakce | 1 |  | ✔ |
| akutní bronchitida | náhlý zánět průdušek | 3 |  | ✔ |
| akutní generalizovaná exantematózní pustulóza | rychle se šířící vyrážka s plnými malých puchýřků po celém těle | 2 |  |  |
| akutní generalizovaná exantematózní pustulóze (agep) | náhlý výskyt mnoha hnisavých pupínků po celém těle | 1 |  |  |
| akutní generalizovaná exematózní pustulóza | vyrážka s puchýřky po celém těle | 1 |  |  |
| akutní hepatitida | náhlý zánět jater | 1 |  | ✔ |
| akutní myokarditidy | náhlý zánět srdečního svalu | 1 |  | ✔ |
| akutní nekomplikovaná cystitida | nekomplikovaný zánět močového měchýře | 1 |  | ✔ |
| akutní otitis media | náhlý zánět středního ucha | 1 |  | ✔ |
| akutní pankarditidy | náhlý zánět všech vrstev srdce | 1 |  | ✔ |
| akutní pankreatitida | náhlý zánět slinivky břišní | 3 |  |  |
| akutní renální selhání | náhlé přestat ledvinami, která přestane filtrovat odpad z krve | 1 |  |  |
| akutní selhání jater | náhle nastalé přestat fungovat jater | 1 |  |  |
| akutní selhání ledvin | Náhle přestaly ledviny plnit svou funkci | 2 |  |  |
| akutní tubulární nekróza | Odumírání buněk v kanálcích ledvin | 1 |  |  |
| akutním bronchiálním astmatu | náhlém záchvatu dušnosti způsobené astmatem | 1 |  |  |
| alergická dermatitida | zánět kůže způsobený alergií | 1 |  |  |
| alergická trombocytopenie | alergické snížení počtu krevních destiček | 2 |  |  |
| alergická vyrážka | alergická vyrážka | 1 |  |  |
| alergické exantémy | vyrážka způsobená alergií | 2 |  |  |
| alergické kožní reakce | Alergická reakce na kůži | 2 |  |  |
| alergické reakce | alergické reakce | 1 |  |  |
| alergický angioedém | alergický otok kůže a sliznic | 1 |  |  |
| alkalické fosfatázy | Zvýšená hodnota alkalické fosfatázy v krvi | 1 |  |  |
| alopecie | plešatost | 3 |  |  |
| amence | dezorientace a zmatenost | 1 |  |  |
| amnézie | ztráta paměti | 1 |  |  |
| an orektální diskomfort | nepříjemný pocit v konečníku | 1 |  |  |
| anafylaktická reakce | Závažná alergická reakce | 3 |  |  |
| anafylaktická reakce/šok | těžká, život ohrožující alergická reakce | 1 |  |  |
| anafylaktické reakce | těžká alergická reakce | 3 |  |  |
| anafylaktické/anafylaktoidní reakce | těžká alergická reakce nebo podobná reakce, která není vyvolána alergií | 1 |  |  |
| anafylaktický šok | Smrtelná alergická reakce | 9 |  |  |
| anafylaktoidní reakce | Reakce připomínající silnou alergii, i když není způsobena alergií | 2 |  |  |
| anafylaxe | těžká alergická reakce ohrožující život | 2 |  |  |
| anginózní stavy | bolesti na hrudi způsobené nedostatkem kyslíku v srdci | 1 |  |  |
| angioedém | otok kůže a sliznic | 13 |  |  |
| angioneurotický edém | rychlý otok kůže a sliznic | 3 |  |  |
| anorexie | nechuť k jídlu | 1 |  |  |
| antinukleární protilátky | Přítomnost protilátek proti jádru buněk | 1 |  |  |
| anémie | malátnost z nedostatku červených krvinek | 1 |  |  |
| aplastická anemie | Neschopnost kostní dřeně tvořit dostatek nových krvinek | 1 |  |  |
| artralgie | bolest kloubů | 3 |  |  |
| arytmie | nerovnoměrný tep srdce | 1 |  |  |
| aseptická meningitida | zánět blan mozku způsobený lékem | 1 |  |  |
| astenie | Slabost a vyčerpání | 4 |  |  |
| astenie, únava a malátnost | slabost, únavu a pocit nemoci | 1 |  |  |
| astma bronchiale i.typu | alergické astma | 1 |  | ✔ |
| astmatický záchvat | záchvat astmatu | 1 |  |  |
| astmoidní bronchitida | zánět průdušek s dušností jako u astmatu | 3 |  | ✔ |
| atopická dermatitida | atopický ekzém | 1 |  | ✔ |
| atrioventrikulární blok prvního stupně | Zpomalené vedení signálu v srdci | 1 |  |  |
| atrofických kožních onemocněních | onemocnění se ztenčenou kůží | 1 |  | ✔ |
| atrofie kůže | Ztenčení kůže | 2 |  |  |
| barevné změny kůže | Změna barvy pleti | 2 |  |  |
| bicytopenie | Snížení počtu dvou druhů krvinek v krvi | 1 |  |  |
| bilirubinemie | zvýšená hladina bilirubinu v krvi (může způsobit nažloutnutí kůže) | 1 |  |  |
| bolest a svalové křeče hrudních a zádových svalů | Bolest a křeče ve svalech na hrudi a zádech | 1 |  |  |
| bolest bederní páteře | bolest bederní páteře | 1 |  |  |
| bolest břicha | bolest břicha | 4 |  |  |
| bolest břicha a břišní diskomfort | bolest nebo nepohodlí v břiše | 1 |  |  |
| bolest břicha průjem | bolest břicha a řídká stolice | 1 |  |  |
| bolest hlavy | bolest hlavy | 17 |  |  |
| bolest horní i dolní části břicha | bolest v břiše | 1 |  |  |
| bolest kloubů | bolest kloubů | 1 |  |  |
| bolest končetin | bolest rukou nebo nohou | 1 |  |  |
| bolest krku | bolest v krku nebo šíji | 1 |  |  |
| bolest na hrudi | bolest na prsou | 1 |  |  |
| bolest svalů | bolest svalů | 1 |  |  |
| bolest v epigastriu | bolest žaludku pod hrudní kostí | 1 |  |  |
| bolest v horní polovině břicha | Bolest ve střední části břicha pod žebry | 1 |  |  |
| bolest v místě aplikace | Bolestivost tam, kde se lék nanáší | 1 |  |  |
| bolest v místě injekce | bolest na místě vpichu jehly | 1 |  |  |
| bolest v nadbřišku | bolest v horní části břicha pod žebry | 1 |  |  |
| bolest vertebrogenního původu | bolest způsobená problémy se zády | 1 |  |  |
| bolest zad | bolest v zádech | 1 |  |  |
| bolest zubů | bolest zubů | 1 |  |  |
| bolesti hlavy | bolest hlavy | 4 |  | ✔ |
| bolesti vertebrogenního původu | bolest vycházející z páteře | 2 |  | ✔ |
| bolesti zubů | bolest zubů | 3 |  | ✔ |
| bolestivá menstruace | bolestivá menstruace | 1 |  | ✔ |
| bradykardie | Pomalý tep srce | 1 |  |  |
| bronchiektázie | trvale rozšířené průdušky | 3 |  | ✔ |
| bronchiolitida | zánět nejmenších průdušek | 3 |  | ✔ |
| bronchiální astma | astma | 3 |  | ✔ |
| bronchospasmus | křeč dýchacích cest | 4 |  |  |
| bronchospasmus (analgetické astma) | zúžení průdušek způsobující potíže s dýcháním podobné záchvatu astmatu | 1 |  |  |
| bronchospasmus – převážně u pacientů s hyperreaktivním bronchiálním systémem ve spojitosti s bronchiálním astmatem | Náhle se stahování průdušek, což způsobí dušení, hlavně u lidí s přecitlivělými dýchacími cestami spojenými s astmou | 1 |  |  |
| bronchospazmus | křeč dýchacích cest | 2 |  |  |
| bronchospazmus (analgetické astma) | zúžení dýchacích cest vyvolané užíváním léku proti bolesti | 1 |  |  |
| bulózní erupce | vyrážka s puchýři | 1 |  |  |
| bulózní exantémy včetně erythema multiforme, stevens-johnsonova syndromu a toxické epidermální nekrolýzy | závažné kožní reakce s tvorbou puchýřů a odlupováním kůže | 1 |  |  |
| bulózní exfoliativní dermatitida | zánět kůže s tvorbou puchýřů a odlupováním vrstev | 1 |  |  |
| břišní diskomfort | nepříjemný pocit v břiše | 1 |  |  |
| břišní distenze | Nafouknuté a oteklé břicho | 1 |  |  |
| břišní distenze a nadmutí břicha | nadýmání v břiše | 1 |  |  |
| břišní křeče | svírání v břiše | 1 |  |  |
| cefalea | bolest hlavy | 1 |  |  |
| celkový útlum s rizikem snížené pozornosti 1 (někdy naopak excitace) 1 | celková ospalost a nebezpečí, že budete méně pozorní (občas může nastat místo toho podrážděnost) | 1 |  |  |
| celulitida | rozlitého zánětu kůže | 1 |  |  |
| celulitida v místě aplikace | Hnisavý zánět podkoží na miste aplikace | 1 |  |  |
| cholecystitida | Zánět žlučníku | 1 |  |  |
| cholelitiáza | Kamene ve žlučníku | 1 |  |  |
| cholestatická žloutenka | žloutenka způsobená přerušením odtoku žluče z jater | 1 |  |  |
| cholestáza | zástava odtoku žluči z jater | 1 |  |  |
| choroby dolní části gastrointestinálního traktu: vředy tenkého střeva (jejunum a ileum) a tlustého střeva (tračník a rektum), kolitida a perforace střeva | Vředy na tenkém a tlustém střevě, zánět střeva a protnutí stěn střeva | 1 |  |  |
| choroby horní části gastrointestinálního traktu: ezofagitida, erozivní duodenitida, erozivní gastritida, ezofageální ulcerace, perforace | Nemoci jícnu a dvanáctníku, včetně zánětu, odřenín sliznice, vředů a protnutí stěn | 1 |  |  |
| chronická bronchitida | dlouhodobý zánět průdušek | 3 |  | ✔ |
| chronická hepatitida | Dlouhodobý zánět jater | 1 |  |  |
| cystitida | zánět močového měchýře | 1 |  | ✔ |
| cytolytická hepatitida | zánět jater s poškozením jejich buněk | 1 |  |  |
| cytolytická hepatitida, která může vést k akutnímu selhání jater | zánět jater vedoucí k vážnému selhání jaterní funkce | 2 |  |  |
| degenerativní ekzém | ekzém ze stárnutí kůže | 1 |  | ✔ |
| dehydratace | odvodnění těla | 2 |  |  |
| dekompenzované srdeční selhání | srdeční selhání, které se vymklo kontrole | 1 |  | ✔ |
| deprese | deprese | 2 |  |  |
| deprese (a zhoršení všech příznaků) | depresivní stav a zhoršení všech příznaků | 1 |  |  |
| depresivní nálada | Smutná nálada a sklíčenost | 1 |  |  |
| dermatitida | zánět kůže | 1 |  |  |
| dezorientace | ztráta orientace v čase, prostoru nebo událostech | 1 |  |  |
| dezorientace (a z horšení všech příznaků) | zmatenost a zhoršení všech příznaků | 1 |  |  |
| diarea | průjem | 1 |  |  |
| duodenálních vředů | vředy ve dvanáctníku | 1 |  | ✔ |
| dušnost | těžkosti s dýcháním a nedostatky vzduchu | 4 |  |  |
| dysfunkce oddiho svěrače | porucha funkce chlopně, která reguluje tok trávicích šťáv do střeva | 1 |  |  |
| dysgeuzie | porucha chuti, nepříjemná pachuť | 2 |  |  |
| dyshidrotický ekzém | ekzém s puchýřky na dlaních a chodidlech | 1 |  | ✔ |
| dyspepsie | trávicí obtíže | 3 |  |  |
| dyspepsie (nauzea, zvracení, zácpa) | porucha trávení (nevolnost, zvracení, zácpa) | 1 |  |  |
| dyspnoe | Zadýchanost nebo dušení | 4 |  |  |
| edém jazyka | otok jazyka | 1 |  |  |
| edém jazyka, a systémovými příznaky (dress) | otok jazyka a celkové příznaky reakce | 1 |  |  |
| edém obličeje | otok obličeje | 2 |  |  |
| edém očních víček | otok očních víček | 2 |  |  |
| edém plic | překrvení plící a přítomnost tekutiny v nich | 1 |  |  |
| edém plic (při vysokých dávkách, zejména u osob s porušenými plicními funkcemi) | otok plic, kdy se v nich hromadí tekutina | 1 |  |  |
| edém rtů | otok rtů | 2 |  |  |
| edém v místě aplikace | Otok na miste aplikace | 1 |  |  |
| ekzém | ekzém | 1 |  |  |
| ekzém u dětí | dětský ekzém | 1 |  | ✔ |
| encefalopatie u pacientů s již existující poruchou jater | narušení funkce mozku u lidí se stávajícími problémy v játrech | 1 |  |  |
| eozinofilie | vysoký počet eozinofilů v krvi | 2 |  |  |
| epigastrický diskomfort | Nepříjemný pocit v horní části břicha pod žebry | 1 |  |  |
| epistaxe | krvácení z nosu | 3 |  |  |
| erythema multiforme | mnohotvará červená vyrážka s puchýřky | 5 |  |  |
| erythema nodosum | zánět krevních cév na nohou a jinde | 3 |  |  |
| erytém | začervenání kůže | 5 |  |  |
| erytém erythema multiforme | zčervenání kůže s více tvary | 1 |  |  |
| erytém v místě aplikace | Zarudnuti kůže na miste aplikace | 1 |  |  |
| euforie/dysforie | pocit eufórie neboli nadměrného štěstí, nebo naopak nepříjemný stav úzkosti a smutku | 1 |  |  |
| euforie/dysforie (při vysokých dávkách) | náhlé výkyvy nálad od nadměrné radosti až po hlubokou smutek nebo podrážděnost | 1 |  |  |
| exantém | vyrážka | 4 |  |  |
| exfoliativní dermatitida | Těžký zánět kůže s olupováním | 1 |  |  |
| ezofagitida | zánět jícnu | 1 |  |  |
| faryngitida | zánět hltanu | 1 |  |  |
| faryngolaryngeální bolest | bolest v krku a hrtanu | 1 |  |  |
| fixní erupce | Zánět na kůži, který se objevuje na stejném místě při opakovaném užívání léku | 1 |  |  |
| fixní lékový exantém | stálá červená skvrna na kůži, která se objevuje při užívání určitého léčiva | 1 |  |  |
| flatulence | plynatost | 1 |  |  |
| flebitida | Zánět žily | 1 |  |  |
| folikulitida v místě aplikace | Zánět vlasového vlasu na miste aplikace | 2 |  |  |
| fotosenzitivita | přecitlivělost na slunce | 4 |  |  |
| fraktury celkového proximálního femuru, distálního konce předloktí a obratlů | zlomeniny kyčelní kosti, předloktí nebo obratle | 1 |  |  |
| gastralgie | bolest žaludku | 1 |  |  |
| gastritida | Zánět žaludku | 1 |  |  |
| gastroezofageální refluxní choroba | Odtok kyseliny ze žaludku do jícnu a trávicí potíže | 1 |  |  |
| gastrointestinální kandidóza | plísňová infekce trávicího traktu | 1 |  |  |
| gastrointestinální perforace | prorazití stěny trávicího traktu | 1 |  |  |
| gastrointestinální poruchy | Problémy v trávicím traktu | 1 |  |  |
| gastrointestinální ulcerace | vředy v trávicím traktu | 1 |  |  |
| glosodynie | bolest jazyka | 1 |  |  |
| gynekomastie | zvětšení prsou u mužů | 3 |  |  |
| gynekomastie 2 | zvětšení prsních žláz u mužů | 1 |  |  |
| haemorrhagia | krvácení | 1 |  |  |
| halucinace | vidění slyšení věcí, které nejsou | 5 |  |  |
| hematochezie (krev ve stolici) | krvácení do stolice | 1 |  |  |
| hemolytická anemie u pacientů s nedostatkem glukóza-6-fosfátdehydrogenázy | Rozpad červených krvinek u lidí, kteří mají dědičný nedostatek specifického enzymu | 1 |  |  |
| hemolytická anémie | rozpad červených krvinek vedoucí k chudokrevnosti | 3 |  |  |
| hepatitida | zánět jater | 2 |  |  |
| hepatitida se žloutenkou nebo bez ní | zánět jater s žloutenkou nebo bez ní | 1 |  |  |
| hepatobiliární infekce | infekce jater a žlučových cest | 1 |  | ✔ |
| hepatocelulární poškození, ikterus | poškození jaterních buněk a žloutenka | 1 |  |  |
| hepatocelulární selhání | selhání funkce jater | 1 |  |  |
| hidróza | nadměrné pocení | 1 |  |  |
| horečka | zvýšená tělesná teplota | 5 |  | ✔ |
| hyperaluminemie | vysoký obsah hliníku v krvi | 1 |  |  |
| hyperglykemie | vysoký obsah cukru v krvi | 1 |  |  |
| hyperhidróza | nadměrné pocení | 2 |  |  |
| hyperlipidemie a zvýšení lipidů (triglyceridů a cholesterolu) | vysoká hodnota tuků v krvi, včetně triglyceridů a cholesterolu | 1 |  |  |
| hypermagnesemie | vysoký obsah hořčíku v krvi | 1 |  |  |
| hyperoxalemie | příliš mnoho kyseliny šťavelové v krvi | 1 |  |  |
| hyperoxalurie | příliš mnoho kyseliny šťavelové ve vzorku moči | 1 |  |  |
| hypersensitivita (včetně anafylaktické reakce a anafylaktického šoku) | přecitlivělost, včetně těžké alergické reakce a alergií šoku | 1 |  |  |
| hypersenzitivita | přecitlivělost | 1 |  |  |
| hypersenzitivní reakce | Přecitlivělost | 7 |  |  |
| hypersenzitivní reakce (jako anafylaxe, angioedém, dyspnoe, svědění, vyrážka a kopřivka) | Těžká alergie včetně otoku dýchacích cest a kůže, potíží s dechem, svěděním, vyrážkou a kopřivky | 1 |  |  |
| hypersenzitivní vaskulitida | zánět cév způsobený přecitlivělostí na lék | 1 |  |  |
| hypertonie svalů | zkrácení a ztuhlost svalů | 1 |  |  |
| hypertrichóza | Nadbytky chlupu | 1 |  |  |
| hypertyreóza | zrychlená činnost štítné žlázy | 1 |  |  |
| hypestezie | snížený cit v kůži | 1 |  |  |
| hypofosfatemie při nadměrných dávkách, dlouhodobém užívání nebo dokonce i při normálních dávkách u pacientů s dietou zaměřenou na nízký obsah fosforu nebo u dětí mladších 2 let se může projevit zvýšenou kostní resorpcí, hyperkalciurií a osteomalacií | nízký obsah fosfátů v krvi po vysokých dávkách, dlouhodobém užívání nebo při dietě s málo fosforem a u dětí do 2 let může vést k úbytku kostní hmoty, zvýšenému množství vápníku v moči a změkčení kostí | 1 |  |  |
| hypoglykemické kóma | koma způsobené příliš nízkou hladinou cukru v krvi | 1 |  |  |
| hypoglykemie | Nízká hladina cukru v krvi | 5 |  |  |
| hypokalcémie | nízký obsah vápníku v krvi | 1 |  |  |
| hypokalémie | nízký obsah draslíku v krvi | 1 |  |  |
| hypomagnezémie | nízký obsah hořčíku v krvi | 2 |  |  |
| hyponatrémie | nízký obsah sodíku v krvi | 2 |  |  |
| hypotenze | nízký krevní tlak | 5 |  | ✔ |
| ikterus | Žloutenka, nažloutnutí kůže a očí | 1 |  |  |
| ileus | střevní paralytický stav (zástava stříva) | 1 |  |  |
| imunitně zprostředkovaná nekrotizující myopatie | svalová choroba vyvolaná imunitním systémem s odumíráním svalů | 1 |  |  |
| insomnie | nespavost | 6 |  |  |
| intermitentní klaudikace | Bolest v nohách při chůzi způsobená nedostatkem krevního zásobení | 1 |  |  |
| intersticiální nefritida | zánět mezičásti ledviny | 3 |  |  |
| intrakraniální hypertenze | vysoký tlak uvnitř lebky | 1 |  |  |
| intrakraniální krvácení | Krvácení uvnitř lebky | 1 |  |  |
| jaterní selhání | selhání funkce jater | 1 |  |  |
| kandidóza sliznic a kůže | plísňové onemocnění sliznic a kůže | 1 |  |  |
| kardiogenní šok | šok ze selhání srdce | 1 |  | ✔ |
| kloubní efuze | nadbytek tekutiny v kloubu | 1 |  |  |
| kolitida související s antibiotiky (včetně pseudomembranózní kolitidy a hemorhagické kolitidy) | zánět střeva způsobený užíváním antibiotik (včetně vážného zánětu s plátovitým povlakem nebo krvácením) | 1 |  |  |
| kolitida včetně ischemické kolitidy | zánět střeva včetně zánětu způsobeného nedostatkem krve | 1 |  |  |
| komplikované intraabdominální infekce | komplikované infekce v dutině břišní | 1 |  | ✔ |
| komunitní pneumonie | zápal plic získaný mimo nemocnici | 1 |  | ✔ |
| kontaktní alergie | alergická reakce po dotyku | 1 |  |  |
| kontaktní ekzém | ekzém z dotyku s dráždivou látkou | 1 |  | ✔ |
| kopřivka | kopřivka | 19 |  | ✔ |
| kopřivka (urticaria) | kopřivka | 1 |  |  |
| kopřivka (urtikarie) | kopřivka, projevující se svěděnými červenými pupínky na kůži | 1 |  |  |
| kounisův syndrom | alergická reakce srdce způsobená uvolněním látek při alergii | 2 |  |  |
| kožní amyloidóza | Nahromadění zvláštní bílkoviny v kůži | 1 |  |  |
| kožní fisury | Praskliny v kůži | 2 |  |  |
| kožní poruchy | nemoci kůže | 1 |  |  |
| kožní projevy včetně psoriziformních kožních změn nebo exacerbace psoriázy (viz bod 4.4) | Úpravy na kůži připomínající lupénku nebo zhoršení lupénky | 1 |  |  |
| kožní vyrážka | vyrážka na kůži | 2 |  |  |
| krvácení | Krvácení | 2 |  |  |
| krvácení z dásní | krvácení ze dvanácti | 1 |  |  |
| krystalurie (včetně akutního poškození ledvin) | přítomnost krystalů v moči, což může vést k náhlému selhání ledvin | 1 |  |  |
| kýchání | kíchání | 1 |  |  |
| křeče | nekontrolovatelné svalové křeče | 2 |  |  |
| laryngitida | zánět hrtanu | 3 |  | ✔ |
| lehké bolesti hlavy | lehké bolesti hlavy | 1 |  |  |
| leukocytopenie | nízký počet bílých krvinek | 2 |  |  |
| leukopenie | nízký počet bílých krvinek | 7 |  |  |
| lichenoidní léková reakce | zánětlivá reakce kůže vyvolaná lékem připomínající lišejník | 1 |  |  |
| lineární iga bulózní dermatóza | autoimunitní kožní nemoc s puchýři způsobená imunitním systémem | 2 |  |  |
| lingua villosa nigra | černý ochlupený jazyk | 1 |  |  |
| lokální kožní reakce | podráždění kůže na místě aplikace | 1 |  |  |
| lupus like syndrom | Nemoc podobná lupusu | 1 |  |  |
| lupus-like syndrom | příznaky připomínající lupénku (nebo systémový lupus) | 1 |  |  |
| lyellův syndrom | velmi těžká alergická reakce s rozsáhlým odlupováním vrchní vrstvy kůže | 1 |  |  |
| lyellův syndrom (ten) | těžká reakce s rozsáhlým odlupováním kůže | 1 |  |  |
| léková horečka | Horečka způsobená lékem | 1 |  |  |
| léková hypersenzitivita | Alergická reakce na lék | 1 |  |  |
| léková interakce s eozinofilií a systémovými symptomy (dress) | těžká reakce na lék spojená se zvýšeným počtem určitých bílých krvinek a celkovými příznaky | 1 |  |  |
| léková reakce s eozinofilií a systémovými příznaky (dress syndrom) | Těžká alergická reakce na lék se zvýšením eosinofilů a postižením vnitřních orgánů | 1 |  |  |
| léková reakce s eozinofilií a systémovými příznaky (dress) | těžká alergická reakce na lék se zvýšením jistých buněk v krvi a příznaky celého těla | 1 |  |  |
| léky indukované poškození jater včetně akutní hepatitidy | poškození jater způsobené lékem včetně zánětu jater | 1 |  |  |
| malátnost | pocit nemoci nebo slabosti | 2 |  |  |
| megakolon | roztažení a zvětšení tlustého střeva | 1 |  |  |
| menstruační poruchy | poruchy měsíčkování | 1 |  |  |
| metabolická acidóza | překyselení krve z poruchy látkové výměny | 1 |  | ✔ |
| metabolická acidóza s vysokou aniontovou mezerou | porucha kyselosti krve | 4 |  |  |
| methemoglobinemie | porucha krevního barviva, kdy krev nepřenáší dost kyslíku | 1 |  | ✔ |
| mikroskopická kolitida | zánět tlustého střeva viditelný pouze pod mikroskopem | 2 |  |  |
| mióza | zúžená zornička oka | 1 |  |  |
| mukoviscidóza | dědičná nemoc s hustým hlenem v plicích | 3 |  | ✔ |
| multiformní erytém | puchýřnatá vyrážka na kůži | 1 |  |  |
| myalgie | bolest svalů | 4 |  |  |
| myasthenia gravis | choroba způsobující svalovou slabost | 1 |  |  |
| mykotické kožní infekce | Plísňové infekce kůže | 1 |  |  |
| myoklonie | náhlé trhavé svalové záškuby | 1 |  |  |
| myopatie | choroba svalů | 1 |  |  |
| myositida | zánět svalů | 1 |  |  |
| mírné bolesti hlavy | mírná bolest hlavy | 1 |  |  |
| nadměrné pocení | nadměrné pocení | 1 |  |  |
| nadměrné říhání | časté říhání | 1 |  |  |
| nadýmání | Oteklý a nafouknutý pocit v břiše | 1 |  |  |
| nausea / zvracení | nevolnost / zvracení | 1 |  |  |
| nausea/zvracení | nevolnost/zvracení | 1 |  |  |
| nauzea | nevolnost | 14 |  |  |
| nazofaryngitida | zánět nosohltanu | 1 |  |  |
| nechutenství | ztráta chuti k jídlu | 1 |  |  |
| nefropatie | Onemocnění ledvin | 1 |  |  |
| nekardiální plicní edém při chronickém užívání a v souvislosti s reakcí přecitlivělosti vyvolané kyselinou acetylsalicylovou | Nahromadění tekutiny v plicích způsobené dlouhodobým užitím léku nebo alergickou reakcí na něj (vylučováno z jiných příčin než srdečního selhání) | 1 |  |  |
| neklasifikovatelný ekzém | ekzém bez určeného druhu | 1 |  | ✔ |
| neklid | neklid | 2 |  |  |
| neléčená adrenální insuficience | neléčená nedostatečnost nadledvin | 1 |  | ✔ |
| neléčená hypertyreóza | neléčená zvýšená činnost štítné žlázy | 1 |  | ✔ |
| neléčená hypofyzární insuficience | neléčená nedostatečnost podvěsku mozkového | 1 |  | ✔ |
| neléčený feochromocytom | neléčený nádor nadledvin tvořící hormony | 1 |  | ✔ |
| neostré vidění | nejasné vidění | 1 |  |  |
| nervozita | rozčilenost | 1 |  |  |
| nespavost | nespavost | 2 |  |  |
| neuralgie | bolest nervů | 3 |  | ✔ |
| neutropenie | nízký počet neutrofilů (druh bílých krvinek) | 2 |  |  |
| nevolnost | Nevolnost | 6 |  |  |
| noční můry | strašné sny během spánku | 3 |  |  |
| numulární ekzém | ekzém v kulatých ložiscích | 1 |  | ✔ |
| nárůst tělesné hmotnosti | přibírání na váze | 1 |  |  |
| návaly horka | náhlý pocit horka | 1 |  |  |
| návaly potu | nenadálé a silné pocení | 1 |  |  |
| období kojení | kojení | 1 |  | ✔ |
| obtíž s močením | potíže při močení | 1 |  |  |
| oběhové selhání u předčasně narozených dětí s nízkou porodní hmotností | selhání krevního oběhu u nedonošených kojenců s malou váhou | 1 |  |  |
| ospalost | ospalost | 3 |  |  |
| otok jazyka | otok jazyka | 1 |  |  |
| otok kloubů | nátoky v kloubech | 1 |  |  |
| otok obličeje | otok obličeje | 1 |  |  |
| otok očních víček | otok očních víček | 1 |  |  |
| otok rtů | otok rtů | 1 |  |  |
| oxalátové močové kameny | kamene v moči z oxalátu | 1 |  |  |
| oční forma myastenie | svalová slabost postihující oči | 1 |  |  |
| palpitace | bušení srdce | 5 |  |  |
| pancytopenie | pokles všech krevních buněk | 8 |  |  |
| pancytopenie (ojedinělé případy) | snížení počtu všech typů krevních buněk (krevní destičky, bílé krvinky i červené krvinky) | 1 |  |  |
| pankreatitida | zánět slinivky břišní | 3 |  |  |
| papuly v místě aplikace | Malé útvary v kůži (hrbolíčky) tam, kde se lék nanáší | 1 |  |  |
| papulózní exantém | drobné pupínky na kůži | 1 |  |  |
| papulózní vyrážka | vyrážka s hrudkovitými výrůstky | 2 | 1 |  |
| paradoxní stimulace cns | nečekané rozrušení nervového systému | 1 |  |  |
| paralytickém ileu | když přestala fungovat střeva a hromadí se v nich obsah | 2 |  |  |
| parestezie | brnění nebo mravenčení | 4 |  |  |
| parestezie v místě aplikace | Ztráta citlivosti na miste aplikace | 1 |  |  |
| parestézie | brnění nebo mravenčení | 1 |  |  |
| peptický vřed s krvácením | Rána na žaludeční sliznici nebo dvanáctníku, která začne krýt | 1 |  |  |
| perforace peptického vředu | Protržení rány na žaludeční sliznici nebo dvanáctníku skrz stěnu orgánu | 1 |  |  |
| periferní cyanóza a chladné končetiny | Modrou barva kůže na končetinách a chladné ruce nebo nohy | 1 |  |  |
| periferní edém | otoky končetin | 1 |  |  |
| periferní edémy | otoky končetin | 1 |  |  |
| periferní neuropatie | poškození nervů v končetinách způsobující bolest nebo brnění | 1 |  |  |
| periferní otok | nátoky na končetinách (ruce, nohy) | 1 |  |  |
| periorální dermatitida | Zánět kůže kolem úst | 2 |  |  |
| periorální dermatitidě | zánět kůže kolem úst | 1 |  | ✔ |
| plicní infiltrát | Zánětlivý nebo jiný problém v plicích viditelný na snímku | 1 |  |  |
| plynatost | plynatost | 3 |  |  |
| pneumonie | Zánět plic | 1 |  |  |
| pocit pálení na sliznici | pocit pálení v nose | 1 |  |  |
| pocit sucha v ústech | suché ústní dutiny | 1 |  |  |
| pocit suchosti v oku | Suché oči | 1 |  |  |
| podrážděnost | podrážděnost | 2 |  |  |
| podráždění v místě aplikace | Drážděni kůže na miste aplikace | 1 |  |  |
| pokles krevního tlaku | nízký krevní tlak | 2 |  |  |
| pokles krevního tlaku až šok | prudký pokles krevního tlaku vedoucí až do stavu život ohrožujícího kolapsu | 1 |  |  |
| pokles krevního tlaku až šok (ojedinělé případy) | silný pokles krevního tlaku, který může vést ke zhroucení a selhání orgánů | 1 |  |  |
| pokles krevního tlaku, synkopy | pokles krevního tlaku a omdlení | 1 |  |  |
| pokousání zvířetem | rány po uštípnutí nebo kousnutí | 1 |  |  |
| polypy ze žlázek fundu žaludku (benigní) | nezhoubné výrůstky v žaludku | 2 |  |  |
| poléková reakce s eozinofilií | léková reakce se zvýšením určitého typu bílých krvinek | 1 |  |  |
| poléková reakce s eozinofilií a systémovými příznaky (dress) | těžká alergická reakce na lék se zvýšením určitého typu bílých krvinek a dalšími celkovými potížemi | 3 |  |  |
| poranění hlavy | po úderu do hlavy nebo při zlomenině lebky | 1 |  |  |
| porucha funkce ledvin | Problém s prací ledvin | 1 |  |  |
| poruchy akomodace oka | problémy s zaostřováním zraku | 1 |  |  |
| poruchy centrálního nervového sytému | Problémy s mozkem a páteří | 1 |  |  |
| poruchy chuti | změna vnímání chuti | 2 |  |  |
| poruchy jater 2 | poruchy činnosti jater | 1 |  |  |
| poruchy jaterní funkce | selhání nebo špatná činnost jater | 1 |  |  |
| poruchy koordinace | nekoordinované pohyby | 1 |  |  |
| poruchy krvetvorby 2 | poruchy tvorby krve | 1 |  |  |
| poruchy metabolických funkcí 2 | poruchy činností spojených s přeměnou látek v těle | 1 |  |  |
| poruchy mikce 1 | problémy s močením | 1 |  |  |
| poruchy psychiky (zmatenost) 2 | poruchy duševního stavu, zmatenost | 1 |  |  |
| poruchy renální funkce | selhání ledvin | 1 |  |  |
| poruchy spánku | potíže se spánkem | 4 |  |  |
| poruchy spánku u dětí | poruchy spánku u dětí | 1 |  |  |
| poruchy tk 1 , srdečního rytmu a frekvence 1 | problémy s krevním tlakem, se srdečním tepem a jeho rychlostí | 1 |  |  |
| poruchy trávení | potíže s trávením | 2 |  |  |
| poruchy vidění | Nechutné problémy se zrakem nebo rozostření | 1 |  |  |
| poruchy vidění/ rozmazané vidění | problémy se zrakem/nejasné vidění | 1 |  |  |
| poruchy vidění/miosa | problémy se zrakem nebo zvětšené zúžení zorničky | 1 |  |  |
| poruchy vidění/mióza (při vysokých dávkách) | problémy s viděním a zúžení zorniček | 1 |  |  |
| poruchy zraku | problémy se zrakem | 2 |  |  |
| poruchy zraku, zvýšený nitrooční tlak 1 | problémy se zrakem a vysoký tlak uvnitř oka | 1 |  |  |
| posturální hypotenze | Pokles krevního tlaku při vstávání ze sedu nebo z lehu | 1 |  |  |
| poškození jater (především hepatocelulární) | Poškození buněk jater | 1 |  |  |
| poškození jater, zejména hepatocelulární | Poškození buněk jaterní tkáně | 1 |  |  |
| prodloužení doby krvácení a protrombinového času | delší čas potřebný ke srážení krve | 1 |  |  |
| prodloužení qt intervalu | Zpomalený elektrický impulz v srdci viditelný na EKG | 1 |  |  |
| prurigo | svrbivá vyrážka s pupínky | 3 |  |  |
| pruritus | svědění kůže | 10 |  |  |
| průjem | průjem | 13 |  |  |
| průjem nebo zácpa | průjem nebo zácpa | 1 |  |  |
| pseudomembranózní enterokolitida | Těžký zánět střev s vytvořením falešných sliznicích povlaků | 1 |  |  |
| pseudomembranózní kolitida | závažný zánět tlustého střeva s tvorbou povlaků na sliznici | 1 |  |  |
| pseudotumor cerebri | zdvih tlaku v mozku bez nádoru | 1 |  |  |
| psychózy | Ztráta styku s realitou, halucinace nebo bludy | 1 |  |  |
| puchýřky v místě aplikace | Blistry na miste aplikace | 1 |  |  |
| pustuly v místě aplikace | Hnisavé bublinky na kůži tam, kde se lék nanáší | 1 |  |  |
| pyelonefritida | zánět ledvinné pánvičky | 1 |  | ✔ |
| pyodermie | Hnisavá kožní infekce | 1 |  |  |
| pyróza | pálení žáhy | 2 |  |  |
| pálení v místě aplikace | Palení na miste aplikace | 1 |  |  |
| pálení žáhy | Pálení žáhy | 1 |  |  |
| pálení žáhy a nauzea | Pálení žáhy a nevolnost | 1 |  |  |
| přechodná nebo trvalá ztráta sluchu | Časné nebo stálé oslepnutí na uši a nedostatek slyšení | 1 |  |  |
| přerůstání necitlivých organismů | nadměrný růst bakterií, které neovlivňují lék | 1 |  |  |
| přítomnost bílých krvinek v moči | zánětlivé buňky v moči | 1 |  |  |
| quinckeho edém | náhlý otok kůže a sliznic | 3 |  | ✔ |
| rabdomyolýza | rozpad svalových buněk s uvolněním obsahu do krve | 1 |  |  |
| raynaudův syndrom | Změna barvy prstů (bílý, modrý) na chladu nebo při stresu | 1 |  |  |
| reakce v místě vpichu | Podráždění nebo zarudnutí v místě vpichu jehly | 1 |  |  |
| reakce z přecitlivělosti | nadměrná reakce organismu na látku, projevující se alergickými příznaky | 2 |  |  |
| reakce z přecitlivělosti jako quinckeho edém | závažná alergická reakce vedoucí k otoku kůže a sliznic, zejména na obličeji | 1 |  |  |
| reaktivní hyperemie | překrvení kůže nebo sliznic po stažení | 1 |  |  |
| rebound efekt | zvýšené ucpání nosu po vysazení léku | 1 |  |  |
| refluxní ezofagitidy | zánět jícnu z návratu žaludeční šťávy | 2 |  | ✔ |
| renální insuficience manifestovaná primárně jako zvýšené hladiny sérového kreatininu a sérové urey | Selhání ledvin projevující se zvýšenými hodnotami jaterních látek v krvi | 1 |  |  |
| renální selhání | Selhání funkce ledvin | 1 |  |  |
| retence kyseliny močové | Nadměrná hromadění látky, která může vést k dně (zánět kloubů) | 1 |  |  |
| retence moči | neschopnost vyprázdnit močový měchýř | 2 |  |  |
| reverzibilní agranulocytóza | dočasné vymizení určitých bílých krvinek | 1 |  |  |
| reverzibilní hyperaktivita | dočasné zvýšené pohnutí nebo neklid | 1 |  |  |
| reverzibilní leukopenie (včetně neutropenie) | dočasné snížení počtu bílých krvinek | 1 |  |  |
| reverzibilní neutropenie | Zpětně se upravující nízký počet bílých krvinek | 1 |  |  |
| reyeův syndrom | Vzácná, ale závažná nemoc postihující játra a mozek, převážně u dětí | 1 |  |  |
| rhinitis sicca | suchá rýma | 1 |  | ✔ |
| rosacee | růžovka | 1 |  | ✔ |
| rozmazané vidění | nejasné vidění | 1 |  |  |
| rozmazané vidění(viz také bod 4.4.) | Mazani videni (viz take bod 4.4.) | 1 |  |  |
| ruptura svalu | roztržení svalu | 1 |  |  |
| ruptura šlachy | prasknutí šlachy | 1 |  |  |
| rýma alergická | Zánět nosu vyvolaný alergií, se skvrnitým výtokem a kýcháním | 1 |  |  |
| salmonelové infekce (přenašeč) | nákaza salmonelou u přenašeče bez příznaků | 1 |  | ✔ |
| sedace | silná ospalost a letargie | 1 |  |  |
| sedativní účinek | uspávání nebo ospalost | 1 |  |  |
| selhání jater | náhlé nebo postupné přestání fungovat jater | 1 |  |  |
| selhání kostní dřeně | Nestárnutí kostní dřeně, která přestane tvořit krevní buňky | 1 |  |  |
| selhání ledvin | selhání ledvin | 1 |  |  |
| sensorická nebo senzomotorická periferní neuropatie | poškození nervů mimo mozek a míchu s brněním, ztrátou citu nebo slabostí svalů | 1 |  |  |
| sick sinus syndrom | porucha srdečního rytmu z nemocného sinusového uzlu | 1 |  | ✔ |
| snížená agregace trombocytů | Srážení krve je pomalejší, krev se lépe netvoří v sraženinu | 1 |  |  |
| snížená úroveň vědomí | zmatenost a snížení bdělosti | 1 |  |  |
| snížení tělesné hmotnosti | hubnutí | 1 |  |  |
| somnolence | ospalost | 4 |  |  |
| spasmy trávicí trubice | křeče v zažívacím ústrojí | 1 |  | ✔ |
| spastické dysmenorey | bolestivá menstruace s křečemi | 1 |  | ✔ |
| spastické migrény | silná bolest hlavy ze stažení cév | 1 |  | ✔ |
| srdeční selhání | Srdce nestihá dostatečně pumpovat krev do těla | 1 |  |  |
| srdeční zástava | Zastavení srdce | 1 |  |  |
| status asthmaticus | těžký astmatický záchvat nereagující na léčbu | 1 |  | ✔ |
| stav zmatenosti | zmatení a neschopnost soustředit se nebo orientovat v čase a prostoru | 1 |  |  |
| stevens-johnsonův syndrom | závažná alergická reakce s puchýři na kůži a sliznicích | 2 |  |  |
| stevensův - johnsonův syndrom | těžká alergická reakce postihující kůži a sliznice s puchýři a odlupováním | 2 |  |  |
| stevensův-johnsonův syndrom | Závažná kožní reakce s odlupováním kůže a sliznic | 4 |  |  |
| stevensův-johnsonův syndrom (sjs) | závažná alergická reakce postihující kůži a sliznice, vedoucí k bolesti a odlupování kůže | 1 |  |  |
| stomatitida | zánět sliznic v ústech | 2 |  |  |
| stridor | Zvuk při dýchání způsobený zúžením dýchacích cest | 1 |  |  |
| strie | Pruhy na kůži | 2 |  |  |
| stupor | stāv (stav snižující vědomí) | 1 |  |  |
| střevní obstrukce | Ucpání nebo zablokování střeva | 1 |  |  |
| subakutní kožní lupus erythematodes | kožní forma lupusu s vyrážkou po slunci | 1 |  |  |
| subakutní kožní lupus erythematodes (viz bod 4.4) | chronické onemocnění kůže podobné lupu, které reaguje na slunce | 1 |  |  |
| substituční léčba hypotyreózy | Doplnění chybějících hormonů při nedostatečné činnosti štítné žlázy | 1 |  |  |
| sucho a podráždění v nose, ústech a krku a rebound kongesce | sucho a podráždění v nose, ústech a krku a návrat ucpaného nosu po ustání účinku léku | 1 |  |  |
| sucho v nose | suchost sliznic v nose | 1 |  |  |
| sucho v ústech | suchost v ústech | 8 |  |  |
| sucho v ústech s polykacími obtížemi 1 , žízeň 1 , snížení motility trávicí soustavy s obstipací 1 | suchost v ústech se špatným polykáním, žízeň a zpomalené fungování trávení vedoucí k zácpě | 1 |  |  |
| suchost oka | Sušší oči a pocit písku v očích | 1 |  |  |
| suchost v místě aplikace | Souska na miste aplikace | 1 |  |  |
| suchost v ústech | sucho v ústech | 1 |  |  |
| svalová slabost | slabost svalů | 2 |  |  |
| svalová únava | únava svalů | 1 |  |  |
| svalové křeče | bolestivé stahy svalů | 2 |  |  |
| svalový spasmus (2) | bolestivé stažení svalu | 1 |  |  |
| svědění | svědění | 6 |  |  |
| svědění v místě aplikace | Zapaleni na miste aplikace | 1 |  |  |
| symetrický léky navozený intertriginózní a flexurální exantém (sdrife) (tzv. baboon syndrom) | vyčervenalá vyrážka v ohybech kůže vyvolaná lékem | 1 |  |  |
| syndrom enterokolitidy vyvolaný léky | zánět tenkého a tlustého střeva způsobený lékem | 1 |  |  |
| syndrom podobný sérové nemoci | reakce těla podobná onemocnění z podaných krevních preparátů | 1 |  |  |
| syndrom z vysazení (viz bod 4.4) | Příznaky při ukončení užívání léku | 1 |  |  |
| synkopa | mdloba | 1 |  |  |
| synkopy (při užití vysokých dávek) | mdloba, náhlá ztráta vědomí | 1 |  |  |
| tachykardie | rychlý tep srdce | 7 |  |  |
| tachykardie, palpitace | Rychlý tep srdce, bušení srdce | 1 |  |  |
| teleangiektázie | Pavoučí žilky | 2 |  |  |
| tendinitida | zánět šlachy | 1 |  |  |
| tendinopatie, někdy komplikovaná rupturou | choroba šlachy, která se občas zlomí | 1 |  |  |
| tenesmy močového měchýře | bolestivé nutkání na močení | 1 |  | ✔ |
| tinitus | zvonění v uších | 5 |  |  |
| tinnitus | Zvonění v uších | 2 |  |  |
| tonsilitis | zánět mandlí | 1 |  |  |
| toxická epidermální nekrolýza | těžká kožní reakce s odlupováním a odumíráním kůže | 5 |  |  |
| toxická epidermální nekrolýza (ten) | závažné odlupování kůže | 3 |  |  |
| toxická kožní erupce | otravná vyrážka na kůži | 2 |  |  |
| točení hlavy | točení hlavy | 1 |  |  |
| tremor | trhavý třes | 2 |  |  |
| trombocytopenie | nízký počet krevních destiček | 9 |  |  |
| tubulointersticiální nefritida (tin) (s možnou progresí k renálnímu selhání) | zánět ledvin, který může vést k selhání ledvin | 1 |  |  |
| těžká dehydratace | závažný nedostatek tekutin v těle | 1 |  | ✔ |
| třes | třes | 2 |  |  |
| třetí trimestr těhotenství | poslední třetina těhotenství | 1 |  | ✔ |
| urtika | kopřivka | 1 |  |  |
| urtikarie | kopřivka | 1 |  |  |
| urtikárie | kopřivka | 1 |  |  |
| vaskulitida | zánět krevních cév | 3 |  |  |
| vaskulární purpura | skvrny na kůži způsobené krvácením do podkoží z malých cév | 1 |  |  |
| vertigo | závrať s pocitem rotace okolních předmětů | 4 |  |  |
| vomitus | zvracení | 1 |  |  |
| vyrážka | vyrážka | 12 |  |  |
| vyrážka / exantém / erupce | kožní vyrážka | 1 |  |  |
| vyrážka v místě aplikace | Vyprazdnění na miste aplikace | 1 |  |  |
| vzestup krevního tlaku | zvýšení krevního tlaku | 1 |  |  |
| výrony (návaly) potu | náhlé a intenzivní pocení | 1 |  |  |
| včetně henochovy- schönleinovy purpury | Zánět krevních cév typický pro děti, způsobující vyrážku a bolesti v břiše či kloubech | 1 |  |  |
| vředech | vředy na kůži | 1 |  | ✔ |
| vředová choroba gastroduodena | vředová choroba žaludku a dvanáctníku | 1 |  | ✔ |
| zarudnutí kůže | začervenání kůže | 1 |  |  |
| zhoršení již existujícího atrioventrikulárního bloku | Zhoršení stávající pomalosti vedení signálu v srdci | 1 |  |  |
| zhoršení vizuálně motorické koordinace | problémy se současným využitím zraku a pohybu | 1 |  |  |
| zhoršení vizuálně motorické koordinace a ostrosti vidění (u vyšších dávek nebo u zvláště citlivých pacientů) | problémy s pohybem rukou ovlivněným tím, co vidí, a rozmazaným viděním | 1 |  |  |
| zhoršený sluch | špatnější slyšení | 1 |  |  |
| zlomenina kyčle, zápěstí nebo páteře (viz bod 4.4) | zlomenina kyčle, zápěstí nebo páteře | 1 |  |  |
| zmatenost | zmatek | 4 |  |  |
| zmatenost (zvláště u predisponovaných pacientů, jakož i zhoršení těchto příznaků, kde již jsou přítomny) | zmátlost (zejména u lidí s rizikem) a zhoršení tohoto stavu | 1 |  |  |
| změna barvy zubů | zbarvení zubů | 1 |  |  |
| změny krevního obrazu | změny v krve | 1 |  |  |
| změny tělesné hmotnosti | změna váhy | 1 |  |  |
| zollinger-ellisonova syndromu | nadměrná tvorba žaludeční kyseliny | 1 |  | ✔ |
| zpožděné vyprazdňování žaludku | Pomalé vyprazdňování obsahu z žaludku do střev | 1 |  |  |
| zrakové poruchy | poruchy vidění | 1 |  |  |
| zrudnutí horní části trupu (syndrom rudého muže) | Zrudnutí horní části těla | 1 |  |  |
| zrudnutí horní části trupu a obličeje | Zrudnutí horní části těla a tváře | 1 |  |  |
| ztráta libida | Ztráta sexuální touhy | 1 |  |  |
| ztráta sluchu | snížení sluchu nebo hluchota | 2 |  |  |
| ztráta vědomí | ztráta vědomí | 1 |  |  |
| zvracení | zvracení | 14 |  |  |
| zvracení (zejména na začátku léčby) | odtření žaludečního obsahu ústy | 1 |  |  |
| zvyšování hladiny aspartátaminotransferázy | Zvýšené hodnoty jaterních enzymů v krvi (AST) | 1 |  |  |
| zvýšené hladiny amylázy | Vyšší množství enzymu štěpícího cukry v krvi | 1 |  |  |
| zvýšené hladiny lipázy | Vyšší množství enzymu štěpícího tuky v krvi | 1 |  |  |
| zvýšené hodnoty jaterních testů | vyšší než obvyklé hodnoty ukazatelů pro funkci jater v krevní zkoušce | 1 |  |  |
| zvýšené jaterní enzymy | zvýšení hladiny enzymů v játrech | 1 |  |  |
| zvýšené jaterní enzymy (transaminázy, γ - gt) | zvýšení hodnot jaterních enzymů v krvi | 1 |  |  |
| zvýšené pocení | nadměrné pocení | 1 |  |  |
| zvýšené riziko krvácení | zvětšená pravděpodobnost krvácení | 1 |  |  |
| zvýšené transaminázy | zvýšení jaterních enzymů v krvi | 1 |  |  |
| zvýšeném nitrolebním tlaku | když je v mozku příliš vysoký tlak | 1 |  |  |
| zvýšení ast a/nebo alt (středně silné zvýšení bylo zaznamenáno u pacientů léčených beta-laktamovými antibiotiky, nicméně význam tohoto zjištění není znám) | vyšší hladiny jaterních enzymů v krvi | 1 |  |  |
| zvýšení chuti k jídlu | Zvětšená chuť na jídlo | 1 |  |  |
| zvýšení hladin aminotransferáz | zvýšená hodnota jaterních enzymů v krvi | 1 |  |  |
| zvýšení hladin jaterních enzymů | Vysoké hodnoty jaterních testů v krvi | 1 |  |  |
| zvýšení hladiny alaninaminotransferázy | Zvýšené hodnoty jaterních enzymů v krvi (ALT) | 1 |  |  |
| zvýšení hladiny kreatinfosfokinázy v krvi | vysoká hodnota enzymu kreatinfosfokináza v krvi, který indikuje poškození svalů | 1 |  |  |
| zvýšení jaterních enzymů | Zvýšené hodnoty v krevní zkoušce ukazující na podráždění jater | 1 |  |  |
| zvýšení jaterních enzymů, zvýšení bilirubinu, hepatitida | Změny v krevních testech játry a zánět jater | 1 |  |  |
| zvýšení tělesné hmotnosti | Náběr na váze | 1 |  |  |
| zvýšení tělesné teploty | zvětšení teploty těla | 1 |  |  |
| zvýšený bilirubin | zvýšení hladiny látky zodpovědné za žloutenku v krvi | 1 |  |  |
| zvýšený krevní tlak | vysoký krevní tlak | 1 |  |  |
| zvýšených hodnot jaterních enzymů | zvýšené hodnoty jaterních enzymů | 1 |  |  |
| záchvaty | náhlý výpad vědomí s křečemi svalů | 1 |  |  |
| zácpa | zácpa | 7 |  |  |
| zánět sliznice | zánět vnitřních výstelků těla (např. úst, nosu) | 1 |  |  |
| zánětů sliznice jícnu | zánět sliznice jícnu | 1 |  | ✔ |
| zánětů žaludeční sliznice | léčba zánětu stěny žaludku | 1 |  |  |
| zápcha | zácpa | 1 |  |  |
| závažné kožní reakce | těžké kožní reakce | 1 |  |  |
| závažné kožní reakce, fixní lékový exantém | těžké reakce na kůži a zpevněná červená vyrážka v místě léku | 1 |  |  |
| závažné srdeční selhání | těžké srdeční selhání | 1 |  | ✔ |
| závažném selhání jater | velmi těžkém selhání jater | 1 |  |  |
| závažném srdečním selhání | velmi těžkém selhání srdce | 1 |  |  |
| závislosti na opioidech | když jste závislí na silných prášcích proti bolesti typu opioidů | 1 |  |  |
| závratě | závratě | 10 |  |  |
| závrať | závratě | 5 |  |  |
| závrať, ospalost, nespavost, psychomotorická hyperaktivita, epileptické záchvaty | Závratě, ospalost, neschopnost usnout, nadměrná aktivita, křeče | 1 |  |  |
| zčervenání a suchost kůže 1 , fotosenzitivita | zarudnutí a suchá kůže, citlivost na slunce | 1 |  |  |
| únava | únava | 11 |  |  |
| útlum dechových funkcí | oslabení nebo zpomalení dýchání | 1 |  |  |
| útlum dechových funkcí (při vyšších dávkách nebo u pacientů se zvýšeným nitrolebním tlakem nebo poraněním hlavy) | oslabení dýchání, které může vést k zastavení dýchání | 1 |  |  |
| útlum kostní dřeně | snížená tvorba krevních buněk v kostní dřeni | 1 |  |  |
| úzkost | úzkost | 2 |  |  |
| říhání | říhání | 3 |  |  |
| žaludeční hypersekrece v důsledku hypersenzitivní reakce na kyselinu acetylsalicylovou | Přílišná tvorba žaludečních šťáv vyvolaná přecitlivělostí na lék | 1 |  |  |
| žaludeční potíže | potíže v žaludku | 1 |  |  |
| žaludečních vředů | vředy v žaludku | 1 |  | ✔ |
| žloutenka | zeleknutí kůže a očí | 2 |  |  |

## Termíny, které měly víc laických tvarů

Ponechaný tvar je **tučně**. Ostatní se zahodily – slouží
k posouzení, jestli byl vybrán ten správný.

**papulózní vyrážka**
- **vyrážka s hrudkovitými výrůstky**  (1×)
- drobné, vystouplé pupínky na kůži  (1×)

