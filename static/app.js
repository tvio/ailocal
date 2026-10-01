"use strict";

// Stav obrazovky. `dotaz === null` znamena uvodni vypis leciv, jinak vysledky
// hledani - obojI se kresli TOUZ funkci, protoze API vraci stejny tvar.
const PRAH_VYCHOZI = 0.60;   // namerena hodnota, viz evaluate.py --prahy
const stav = { dotaz: null, sekce: "", prah: PRAH_VYCHOZI,
               strana: 1, razeni: "nazev", smer: "asc", naStrance: 10 };

const $ = (id) => document.getElementById(id);
const prahEl = $("prah");
const prahOut = $("prah-hodnota");
const jistotaEl = $("jistota");
const jistotaOut = $("jistota-hodnota");

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (s) => String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, (c) => ESC[c]);

const anoNe = (v, ano, ne) =>
  v === true ? '<span class="ano">' + ano + "</span>"
  : v === false ? '<span class="ne">' + ne + "</span>"
  : '<span class="tise">?</span>';

const NA = '<span class="tise">NA</span>';

// Frekvence NU v poradi od nejcastejsi. Barva nese vyznam (cervena = casto),
// takze se pozna i bez cteni - u seznamu 40 ucinku je to jediny zpusob,
// jak na prvni pohled odlisit to, co se stane kazdemu desatemu, od
// jednoho z deseti tisic. Hodnoty jsou kanonicke (normalizuj_frekvenci).
const FREKVENCE = ["velmi časté", "časté", "méně časté", "vzácné",
                   "velmi vzácné", "není známo"];
const FREK_TRIDA = { "velmi časté": "f1", "časté": "f2", "méně časté": "f3",
                     "vzácné": "f4", "velmi vzácné": "f5", "není známo": "f6" };
const frekZnacka = (f) => f
  ? '<span class="frek ' + (FREK_TRIDA[f] || "f6") + '">' + esc(f) + "</span>" : "";

// --- cekani na modely -------------------------------------------------------
// Model ma 87 GB a nahrava se pri startu na pozadi. Dokud neni v pameti,
// hledani vraci 503, takze se ceka a ukazuje se PROC - mlcici aplikace
// vypada jako rozbita.
async function pockejNaModely() {
  for (;;) {
    try {
      const s = await (await fetch("/api/stav")).json();
      $("start-text").textContent = s.hlaska;
      if (s.pripraveno) { $("start").hidden = true; return; }
    } catch (e) {
      $("start-text").textContent = "server neodpovídá…";
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
}

// --- nacitani ---------------------------------------------------------------
async function nacti() {
  $("pracuje").hidden = false;
  $("hlaska").hidden = true;
  try {
    const url = stav.dotaz
      ? "/api/hledat?q=" + encodeURIComponent(stav.dotaz) + "&strana=" + stav.strana +
        "&prah=" + stav.prah + (stav.sekce ? "&sekce=" + stav.sekce : "") +
        "&na_strance=" + stav.naStrance
      : "/api/leciva?strana=" + stav.strana + "&razeni=" + stav.razeni + "&smer=" + stav.smer +
        "&na_strance=" + stav.naStrance;

    const odp = await fetch(url);
    if (!odp.ok) {
      const t = await odp.json().catch(() => ({}));
      throw new Error(t.detail || "chyba " + odp.status);
    }
    vykresli(await odp.json());
  } catch (e) {
    $("telo").innerHTML = "";
    $("hlaska").className = "hlaska chyba";
    $("hlaska").textContent = e.message;
    $("hlaska").hidden = false;
  } finally {
    $("pracuje").hidden = true;
  }
}

// --- vykresleni -------------------------------------------------------------
function vykresli(d) {
  vykresliRouter(d.router, d);
  // Co znamena sloupec Nalezeno - rika zahlavi, ne stitek v kazdem radku.
  const th = $("th-nalezeno");
  if (th) th.textContent = !d.dotaz ? "Nalezeno"
    : d.cely_usek ? "Nalezeno (souhrn sekce)" : "Nalezeno (nejlepší shoda)";
  $("telo").innerHTML = d.radky.map((r, i) => radek(r, i, d.cely_usek, d.usek_orezan)).join("");
  // Cteni sekce s 1-2 leky ("davkovani vibrocil"): rozbalit rovnou,
  // proklik je tam zbytecny - clovek chce sekci precist.
  if (d.cely_usek && d.radky.length <= 2) {
    document.querySelectorAll("#telo tr.detail").forEach((tr) => {
      tr.hidden = false;
      const sipka = tr.previousElementSibling && tr.previousElementSibling.querySelector(".sipka");
      if (sipka) sipka.setAttribute("aria-expanded", "true");
    });
  }
  vykresliAtc(d.atc_navrh);
  vykresliStrankovani(d);
  oznacRazeni();
  prebarvi();

  if (!d.radky.length) {
    $("hlaska").className = "hlaska";
    // Rozlisit DVE ruzne pricinny prazdneho vysledku - splynout je do jedne
    // hlasky je zavadejici. "PARALEN nema velmi caste ucinky" je odpoved,
    // kdezto "nic neni dost podobne" zni jako selhani hledani.
    if (!d.dotaz) {
      $("hlaska").innerHTML = "Žádná léčiva.";
    } else if (!d.kandidatu_pred_prahem) {
      $("hlaska").innerHTML =
        "Filtr nepustil dál ani jeden záznam" +
        (d.router && d.router.filtr_popis ? " (" + esc(d.router.filtr_popis) + ")" : "") +
        ". Taková kombinace v datech není — zkuste dotaz bez některého omezení.";
    } else {
      $("hlaska").innerHTML =
        "Filtrem prošlo " + d.kandidatu_pred_prahem +
        " záznamů, ale žádný nedosáhl prahu podobnosti " + d.prah + ".";
    }
    $("hlaska").hidden = false;
  }
}

function vykresliRouter(r, d) {
  const el = $("router");
  if (!r) { el.hidden = true; return; }
  const c = [];
  c.push("<strong>Router:</strong> text pro vektor <code>" + esc(r.dotaz_text) + "</code>");
  if (r.sekce) {
    c.push("sekce <code>" + esc(r.sekce.join(", ")) + "</code>" +
           (r.sekce_vynucena ? " <em>(vynuceno ručně)</em>" : ""));
  }
  if (r.jistota) c.push("jistota <code>" + esc(r.jistota) + "</code>");
  if (r.filtr_popis) c.push("filtr <code>" + esc(r.filtr_popis) + "</code>");
  // Kdyz filtr obsahuje rizenou hodnotu, prah se NEUPLATNUJE - API vrati 0.
  // Musi to byt videt, jinak to vypada, ze posuvnik nefunguje.
  c.push(d.prah > 0
    ? "práh <code>" + d.prah + "</code>"
    : 'práh <code>neuplatněn</code> <em>(filtr je přesný)</em>');
  el.innerHTML = c.join(" · ");
  el.hidden = false;
}

function radek(r, i, celyUsek, orezan) {
  const l = r.lecivo;
  const n = r.nejlepsi;
  const id = "d-" + l.kod_sukl + "-" + i;

  let nalez = '<span class="tise">—</span>';
  if (n && n.obsah_text) {
    // ROZLOZENI BUNKY (1. 10. 2026): znacka sekce PRVNI a s pevnou sirkou,
    // vpravo od ni sloupec se dvema radky - text nalezu a pod nim drobne
    // doplnky. Oba radky zacinaji na stejnem miste (driv se stitky lamaly
    // pres sebe a druhy radek zacinal jinde nez prvni).
    //
    // Doplnky - dva RUZNE udaje, kazdy s vlastnim popiskem:
    //  - skupina u INDIKACE (z 4.1): jen kdyz je znama; „neni uvedeno"
    //    vedle leku, ktery prosel filtrem „dite 12 let", pusobilo jako
    //    neznamy vek. Zkracena, cela v bubline.
    //  - vek pouziti LEKU (4.1–4.3, common/vek.py), podle nej filtruje
    //    „pro dite X let"
    const meta = [];
    if (!celyUsek && n.skupina && n.skupina !== "není uvedeno") {
      const s = n.skupina.length > MAX_SKUPINA ? n.skupina.slice(0, MAX_SKUPINA - 1) + "…" : n.skupina;
      meta.push('<span title="indikace pro: ' + esc(n.skupina) + '">pro: ' + esc(s) + "</span>");
    }
    if ((l.vek_od !== null && l.vek_od !== undefined) || (l.pro_deti !== null && l.pro_deti !== undefined)) {
      meta.push('<span title="věk použití léku podle SPC (4.1–4.3)">' + popisVeku(l) + "</span>");
    }
    let text;
    if (celyUsek) {
      // CTENI SEKCE: souhrn cele sekce, polozky az v rozbaleni. Prvni polozka
      // v radku vypadala jako shrnuti (NU „jen vzacne").
      text = souhrnSekce([n].concat(r.dalsi || []), orezan);
      meta.push("rozbalte ▼");
    } else {
      // HLEDANI: nejlepsi shoda (rika to zahlavi sloupce, ne stitek u radku)
      text = esc(n.obsah_text) + frekZnacka(n.frekvence);
      if (r.dalsi && r.dalsi.length) {
        meta.push("+" + r.dalsi.length + " " +
                  sklon(r.dalsi.length, "shoda", "shody", "shod") + " ▼");
      }
    }
    nalez = '<div class="nalez-box">' + sekceTag(n) +
      '<div class="nalez-obsah"><div class="nalez-text">' + text + "</div>" +
      (meta.length ? '<div class="nalez-meta">' + meta.join(" · ") + "</div>" : "") +
      "</div></div>";
  }

  const strana = n && n.strana_pdf ? n.strana_pdf : "null";
  const titulek = "Otevřít SPC v PDF" + (n && n.strana_pdf ? ", strana " + n.strana_pdf : "");
  const pdf = l.ma_pdf
    ? '<button class="ikona-pdf" title="' + titulek + '" onclick="otevriPdf(\'' +
      l.kod_sukl + "', " + strana + ')">&#128221;</button>'
    : '<button class="ikona-pdf" disabled title="PDF není k dispozici">&#128221;</button>';

  // Rozbaluje CELY radek, ne jen sipka - kliknuti kamkoliv do radku je to,
  // co clovek zkusi jako prvni. Sipka zustava jako vizualni voditko.
  // data-cosine drzi skore, aby slo prebarvit BEZ noveho hledani
  const c = n && n.cosine !== null && n.cosine !== undefined ? n.cosine : "";
  return '<tr class="klikaci" data-cosine="' + c +
    '" onclick="prepniRadek(this, &#39;' + id + '&#39;, event)">' +
    '<td><button class="sipka" aria-expanded="false" aria-controls="' + id +
      '" tabindex="-1">&#9660;</button></td>' +
    // Forma pod nazvem: jedno jmeno a sila maji casto vic SPC (VIBROCIL
    // kapky i sprej) a bez formy by vypadaly jako duplicita.
    '<td class="nazev">' + esc(l.nazev) +
      (l.lekova_forma ? '<br><span class="tise">' + esc(l.lekova_forma) + "</span>" : "") + "</td>" +
    "<td>" + esc(l.sila) + "</td>" +
    '<td class="latky">' + latkyBunka(l.ucinne_latky) + "</td>" +
    "<td>" + anoNe(l.na_predpis, "Rx", "OTC") + "</td>" +
    "<td>" + anoNe(l.hrazeno, "hrazený", "nehrazený") + "</td>" +
    "<td>" + esc(l.atc) + "</td>" +
    "<td>" + esc(l.kod_sukl) + "</td>" +
    '<td class="skore">' + (n && n.cosine !== null && n.cosine !== undefined
                            ? n.cosine.toFixed(3) : "—") + "</td>" +
    "<td>" + nalez + "</td>" +
    "<td>" + pdf + "</td>" +
    "</tr>" +
    '<tr class="detail" id="' + id + '" hidden><td colspan="11">' + detail(r, celyUsek, orezan) + "</td></tr>";
}

// Metadata jsou schvalne ZABALENA - uvodni vypis a vysledek hledani se tim
// nemusi lisit. U vypisu bez hledani jsou skore proste "NA".
function detail(r, celyUsek, orezan) {
  const n = r.nejlepsi;
  const l = r.lecivo;
  const cis = (v, des) => (v === null || v === undefined ? NA : v.toFixed(des));

  let h = "";
  if (celyUsek && n) {
    // Cela sekce (nebo jeji cast podle filtru) jako hlavni obsah rozbaleni.
    h += "<h4>" + (orezan ? "Položky odpovídající filtru" : "Celá sekce") +
         ' <span class="tise">(' + esc(n.sekce_nazev) + ", pořadí podle dokumentu)</span></h4>" +
         obsahSekce([n].concat(r.dalsi || []));
  }

  h += (celyUsek ? "<details><summary>Údaje o léku a skóre</summary>" : "") + "<dl>" +
    "<dt>Kód SÚKL</dt><dd>" + esc(l.kod_sukl) + "</dd>" +
    "<dt>Léková forma</dt><dd>" + (l.lekova_forma ? esc(l.lekova_forma) : "—") + "</dd>" +
    "<dt>Účinné látky</dt><dd>" + ((l.ucinne_latky || []).length ? esc(l.ucinne_latky.join(", ")) : "—") + "</dd>" +
    "<dt>Věk použití</dt><dd>" + popisVeku(l) + "</dd>" +
    "<dt>ATC</dt><dd>" + (l.atc ? esc(l.atc) : "—") + "</dd>" +
    "<dt>Skóre (RRF)</dt><dd>" + cis(r.skore, 6) + "</dd>" +
    "<dt>Odstup od nejlepšího</dt><dd>" +
      (r.odstup === null || r.odstup === undefined ? NA : r.odstup + " / 100") + "</dd>" +
    "<dt>Sémantika (cosine)</dt><dd>" + cis(n ? n.cosine : null, 3) +
      (n && n.poradi_sem ? " · pořadí #" + n.poradi_sem : "") + "</dd>" +
    "<dt>Fulltext (ts_rank)</dt><dd>" + cis(n ? n.fts : null, 4) +
      (n && n.poradi_fts ? " · pořadí #" + n.poradi_fts
        : n ? ' · <span class="tise">nenašel</span>' : "") + "</dd>" +
    "<dt>Sekce</dt><dd>" + (n && n.sekce_nazev ? esc(n.sekce_nazev) : NA) + "</dd>" +
    "<dt>Strana v PDF</dt><dd>" + (n && n.strana_pdf ? n.strana_pdf : NA) + "</dd>" +
    "<dt>Orgánový systém</dt><dd>" +
      (n && n.organovy_system ? esc(n.organovy_system) : NA) + "</dd>" +
    "</dl>" + (celyUsek ? "</details>" : "");

  if (!celyUsek && r.dalsi && r.dalsi.length) {
    // U cele sekce patri do seznamu i nejlepsi polozka - je to prvni
    // polozka sekce a bez ni by nesedely pocty u frekvenci.
    const polozky = celyUsek && n ? [n].concat(r.dalsi) : r.dalsi;
    const id = "f-" + l.kod_sukl + "-" + Math.random().toString(36).slice(2, 8);
    h += "<h4>Další shody <span class=\"tise\">(seřazené podle podobnosti)</span></h4>" +
      frekTlacitka(polozky, id) + '<ul id="' + id + '">' +
      polozky.map((d) =>
        '<li data-frek="' + esc(d.frekvence || "") + '">' + esc(d.obsah_text) +
        frekZnacka(d.frekvence) + ' <span class="tise">(' + esc(d.sekce_nazev) +
        (d.cosine !== null && d.cosine !== undefined ? ", cosine " + d.cosine.toFixed(3) : "") +
        ")</span></li>").join("") + "</ul>";
  }
  // Lek nalezeny podle indikace (kontraindikace): pod dalsi shody i OSTATNI
  // polozky te sekce, ktere s dotazem nesouvisi. Nacita se az pri rozbaleni.
  if (!celyUsek && n && OSTATNI_SEKCE[n.sekce]) {
    const videne = [n].concat(r.dalsi || []).map((d) => d.obsah_text);
    h += '<div class="ostatni" data-kod="' + esc(l.kod_sukl) + '" data-sekce="' + esc(n.sekce) +
         '" data-videne="' + esc(JSON.stringify(videne)) + '"></div>';
  }
  return h;
}

const OSTATNI_SEKCE = { indikace: "Ostatní indikace léku",
                        kontraindikace: "Ostatní kontraindikace léku" };

// Nacte a vykresli ostatni polozky sekce (jen jednou na radek).
async function nactiOstatni(box) {
  if (!box || box.dataset.nacteno) return;
  box.dataset.nacteno = "1";
  box.innerHTML = '<span class="tise">načítám…</span>';
  try {
    const odp = await fetch("/api/lecivo/" + encodeURIComponent(box.dataset.kod) +
                            "/sekce/" + encodeURIComponent(box.dataset.sekce));
    if (!odp.ok) throw new Error("chyba " + odp.status);
    const videne = new Set(JSON.parse(box.dataset.videne || "[]"));
    const zbytek = (await odp.json()).filter((d) => !videne.has(d.obsah_text));
    box.innerHTML = "<h4>" + OSTATNI_SEKCE[box.dataset.sekce] +
      ' <span class="tise">(' + (zbytek.length ? "pořadí podle dokumentu" : "žádné další") + ")</span></h4>" +
      (zbytek.length ? "<ul>" + zbytek.map((d) => "<li>" + esc(d.obsah_text) +
        (d.skupina && d.skupina !== "není uvedeno"
          ? ' <span class="znacka">pro: ' + esc(d.skupina) + "</span>" : "") +
        "</li>").join("") + "</ul>" : "");
  } catch (e) {
    box.dataset.nacteno = "";
    box.innerHTML = '<span class="tise">ostatní položky se nepodařilo načíst (' + esc(e.message) + ")</span>";
  }
}

// Ucinne latky do bunky tabulky: kombinovane pripravky (napr. 0149034) maji
// mnoho latek a roztahly radek na 4 radky pres celou stranku. Ukaze se
// prvni latka (max 50 znaku) a „+ N dalsi"; cely seznam je v tooltipu
// a v detailu leku.
const MAX_LATKA = 50;
function latkyBunka(latky) {
  const l = latky || [];
  if (!l.length) return "—";
  const prvni = l[0].length > MAX_LATKA ? l[0].slice(0, MAX_LATKA - 1) + "…" : l[0];
  const dalsi = l.length - 1;
  return '<span title="' + esc(l.join(", ")) + '">' + esc(prvni) +
    (dalsi ? ' <span class="tise">+ ' + dalsi + " " + sklon(dalsi, "další", "další", "dalších") + "</span>" : "") +
    "</span>";
}

// Znacka sekce: kratky nazev, barva podle sekce, plny nazev v bubline.
const MAX_SKUPINA = 40;
const SEKCE_KRATCE = { indikace: "Indikace", kontraindikace: "Kontraindikace",
                       davkovani: "Dávkování", nezadouci_ucinky: "Nežád. účinky",
                       atributy: "Identita" };
function sekceTag(n) {
  return '<span class="sekce-tag s-' + esc(n.sekce || "") + '" title="' + esc(n.sekce_nazev || "") + '">' +
    esc(SEKCE_KRATCE[n.sekce] || n.sekce_nazev || "") + "</span>";
}

// Cesky plural: 1 polozka, 2-4 polozky, 5+ polozek.
function sklon(n, jedna, dve, pet) {
  return n === 1 ? jedna : (n >= 2 && n <= 4 ? dve : pet);
}

// Souhrn sekce do RADKU (cteni sekce). Polozky jsou az v rozbaleni.
function souhrnSekce(polozky, orezan) {
  const n = polozky.length;
  const s = polozky[0] ? polozky[0].sekce : "";
  const filtr = orezan ? ' <span class="tise">(odpovídá filtru)</span>' : "";
  if (s === "nezadouci_ucinky") {
    const pocty = {};
    polozky.forEach((d) => { const f = d.frekvence || "není známo"; pocty[f] = (pocty[f] || 0) + 1; });
    return "<strong>" + n + " " + sklon(n, "nežádoucí účinek", "nežádoucí účinky", "nežádoucích účinků") +
      "</strong>" + filtr + ": " +
      FREKVENCE.filter((f) => pocty[f]).map((f) =>
        '<span class="frek ' + FREK_TRIDA[f] + '">' + esc(f) + " " + pocty[f] + "</span>").join("");
  }
  if (s === "davkovani") {
    const skupiny = [...new Set(polozky.map((d) => (d.polozka && d.polozka.pacient) || d.obsah_text))];
    return "<strong>" + n + " " + sklon(n, "dávkování", "dávkování", "dávkování") + "</strong>" + filtr +
      ": " + skupiny.slice(0, 4).map(esc).join(" · ") + (skupiny.length > 4 ? " · …" : "");
  }
  const nazvy = { indikace: ["indikace", "indikace", "indikací"],
                  kontraindikace: ["kontraindikace", "kontraindikace", "kontraindikací"] };
  const sl = nazvy[s] || ["položka", "položky", "položek"];
  return "<strong>" + n + " " + sklon(n, sl[0], sl[1], sl[2]) + "</strong>" + filtr + ": " +
    polozky.slice(0, 2).map((d) => esc(d.obsah_text)).join(" · ") + (n > 2 ? " · …" : "");
}

// Obsah sekce v ROZBALENI, usporadany podle smyslu sekce.
function obsahSekce(polozky) {
  const s = polozky[0] ? polozky[0].sekce : "";
  if (s === "nezadouci_ucinky") {
    // Seskupene podle frekvence, nejcastejsi nahore - laik hned vidi, co je bezne.
    const skup = {};
    polozky.forEach((d) => { const f = d.frekvence || "není známo"; (skup[f] = skup[f] || []).push(d); });
    // Tlacitka frekvenci zustavaji: vyber zobrazi jen svou skupinu (i vic naraz).
    const id = "f-" + Math.random().toString(36).slice(2, 8);
    return frekTlacitka(polozky, id) + '<div id="' + id + '">' +
      FREKVENCE.filter((f) => skup[f]).map((f) =>
        '<div data-frek="' + esc(f) + '">' +
        '<h5 class="skupina-frek">' + frekZnacka(f) + ' <span class="tise">' + skup[f].length + "</span></h5>" +
        "<ul>" + skup[f].map((d) => "<li>" + esc(d.obsah_text) +
          (d.organovy_system ? ' <span class="tise">— ' + esc(d.organovy_system) + "</span>" : "") +
          "</li>").join("") + "</ul></div>").join("") + "</div>";
  }
  if (s === "davkovani") {
    const sl = (d, k) => (d.polozka && d.polozka[k]) ? esc(d.polozka[k]) : "";
    return '<table class="davkovani"><thead><tr><th>Pro koho</th><th>Dávka</th>' +
      "<th>Jak často</th><th>Poznámka</th></tr></thead><tbody>" +
      polozky.map((d) => d.polozka
        ? "<tr><td>" + sl(d, "pacient") + "</td><td>" + sl(d, "davka") + "</td><td>" +
          sl(d, "frekvence") + "</td><td>" + sl(d, "poznamka") + "</td></tr>"
        : '<tr><td colspan="4">' + esc(d.obsah_text) + "</td></tr>").join("") +
      "</tbody></table>";
  }
  return "<ul>" + polozky.map((d) => "<li>" + esc(d.obsah_text) +
    (d.skupina && d.skupina !== "není uvedeno"
      ? ' <span class="znacka">pro: ' + esc(d.skupina) + "</span>" : "") + "</li>").join("") + "</ul>";
}

// Tlacitka pro zuzeni seznamu podle frekvence. Filtruje se v prohlizeci
// nad uz nactenymi polozkami - novy dotaz na model by byl zbytecny.
// Nic nevybrano = vse. Ukazuji se jen frekvence, ktere v seznamu JSOU.
function frekTlacitka(polozky, id) {
  const pocty = {};
  polozky.forEach((d) => { if (d.frekvence) pocty[d.frekvence] = (pocty[d.frekvence] || 0) + 1; });
  const je = FREKVENCE.filter((f) => pocty[f]);
  if (!je.length) return "";
  return '<div class="frek-filtr"><span class="tise">zúžit podle četnosti:</span> ' +
    je.map((f) =>
      '<button type="button" class="frek ' + FREK_TRIDA[f] + '" data-f="' + esc(f) +
      '" onclick="prepniFrekvenci(this, \'' + id + '\')">' + esc(f) +
      " (" + pocty[f] + ")</button>").join(" ") + "</div>";
}

window.prepniFrekvenci = function (btn, id) {
  btn.classList.toggle("vybrano");
  const box = btn.parentElement;
  const vybrane = [...box.querySelectorAll("button.vybrano")].map((b) => b.dataset.f);
  box.classList.toggle("aktivni", vybrane.length > 0);
  // Primi potomci s data-frek: polozky <li> (hledani) i skupiny <div> (cteni sekce)
  document.querySelectorAll("#" + id + " > [data-frek]").forEach((li) => {
    li.hidden = vybrane.length > 0 && !vybrane.includes(li.dataset.frek);
  });
};

function vykresliAtc(seznam) {
  const el = $("atc-navrh");
  if (!seznam || !seznam.length) { el.hidden = true; return; }
  el.innerHTML =
    "<h3>Podle terapeutické skupiny (odvozeno z ATC — <em>není to údaj ze SPC</em>)</h3><ul>" +
    seznam.map((l) =>
      "<li>" + esc(l.nazev) + " " + esc(l.sila) + " · " +
      (l.na_predpis ? "Rx" : "OTC") + " · " +
      (l.hrazeno ? "hrazený" : "nehrazený") + " · ATC " + esc(l.atc) + "</li>").join("") +
    '</ul><p class="tise">Skupina říká, k čemu se léčiva tohoto druhu používají. ' +
    "Není to indikace z příslušného SPC — tu je potřeba ověřit.</p>";
  el.hidden = false;
}

// Vek pouziti z SPC 4.1–4.3 (common/vek.py). Popisek je soucast odpovedi:
// musi byt videt, ze je to ODVOZENE a kdy to nejde urcit.
function popisVeku(l) {
  const v = l.vek_od;
  if (v === null || v === undefined) {
    if (l.pro_deti === true) return "pro děti ano, věk v SPC neuveden";
    if (l.pro_deti === false) return "jen dospělí";
    return '<span class="tise">z SPC nejde určit</span>';
  }
  if (v >= 18) return "jen dospělí (od 18 let)";
  if (v <= 0) return "od narození";
  if (v < 1) return "od " + Math.round(v * 12) + " měsíců";
  return "od " + (Math.round(v * 10) / 10) + " let";
}

// Po korpusu (30.9.2026) ma vypis 588 stranek a tlacitko pro kazdou
// zabralo pul obrazovky. Proto jen okenko kolem aktualni stranky:
//   « ‹ 1 … 5 6 [7] 8 9 … 588 › »   + vyber poctu na stranku
const OKENKO = 2;                     // stranek na kazdou stranu od aktualni
const NA_STRANCE_VOLBY = [10, 25, 50, 100];

function tlacitkoStrany(n, text, d, titulek) {
  const neaktivni = n < 1 || n > d.stran || n === d.strana;
  return '<button title="' + titulek + '"' +
         (n === d.strana && text == n ? ' class="aktivni"' : "") +
         (neaktivni ? " disabled" : ' onclick="naStranu(' + n + ')"') + ">" + text + "</button>";
}

function vykresliStrankovani(d) {
  const el = $("strankovani");
  const vyber = '<label class="tise">na stránku <select onchange="zmenNaStrance(this.value)">' +
    NA_STRANCE_VOLBY.map(v => '<option value="' + v + '"' +
      (v === d.na_strance ? " selected" : "") + ">" + v + "</option>").join("") +
    "</select></label>";
  const souhrn = '<span class="tise">' + d.celkem + " záznamů</span>";
  if (d.stran <= 1) {
    el.innerHTML = souhrn + vyber;
    return;
  }
  const b = [tlacitkoStrany(1, "&laquo;", d, "první stránka"),
             tlacitkoStrany(d.strana - 1, "&lsaquo;", d, "předchozí")];
  const od = Math.max(1, d.strana - OKENKO), doo = Math.min(d.stran, d.strana + OKENKO);
  if (od > 1) b.push(tlacitkoStrany(1, 1, d, "stránka 1"));
  if (od > 2) b.push('<span class="tise">…</span>');
  for (let i = od; i <= doo; i++) b.push(tlacitkoStrany(i, i, d, "stránka " + i));
  if (doo < d.stran - 1) b.push('<span class="tise">…</span>');
  if (doo < d.stran) b.push(tlacitkoStrany(d.stran, d.stran, d, "poslední stránka"));
  b.push(tlacitkoStrany(d.strana + 1, "&rsaquo;", d, "další"),
         tlacitkoStrany(d.stran, "&raquo;", d, "poslední stránka"));
  b.push('<span class="tise">stránka ' + d.strana + " z " + d.stran + ", " + d.celkem +
         " záznamů</span>", vyber);
  el.innerHTML = b.join("");
}

// Prebarveni podle jistoty. Delá se v prohlizeci nad uz nactenymi daty -
// posun jezdce NESMI poslat novy dotaz na model, je to jen zvyrazneni.
function prebarvi() {
  const mez = Number(jistotaEl.value);
  document.querySelectorAll("tbody tr.klikaci").forEach((tr) => {
    const c = tr.dataset.cosine;
    const je = c !== "" && Number(c) >= mez;
    tr.classList.toggle("jiste", je);
    tr.classList.toggle("hranicni", c !== "" && !je);
  });
}

function oznacRazeni() {
  document.querySelectorAll("th[data-sort]").forEach((th) => {
    const je = !stav.dotaz && th.dataset.sort === stav.razeni;
    th.classList.toggle("aktivni", je);
    th.textContent = th.textContent.replace(/ [▲▼]$/, "");
    if (je) th.textContent += stav.smer === "asc" ? " ▲" : " ▼";
  });
}

// --- akce -------------------------------------------------------------------
window.prepniRadek = function (tr, id, ev) {
  // Klik na PDF ikonu nebo odkaz radek NEROZBALUJE.
  if (ev && ev.target.closest(".ikona-pdf, a")) return;
  // Kdyz si nekdo oznacuje text, taky ne.
  const vyber = window.getSelection();
  if (vyber && String(vyber).length > 0) return;

  const r = document.getElementById(id);
  r.hidden = !r.hidden;
  if (!r.hidden) nactiOstatni(r.querySelector(".ostatni"));
  const sipka = tr.querySelector(".sipka");
  if (sipka) sipka.setAttribute("aria-expanded", String(!r.hidden));
};

window.otevriPdf = function (kod, strana) {
  // Fragment #page=N umi vestaveny prohlizec PDF - otevre se rovnou u pasaze.
  window.open("/api/pdf/" + kod + (strana ? "#page=" + strana : ""), "_blank");
};

window.zmenNaStrance = function (n) {
  stav.naStrance = parseInt(n, 10);
  stav.strana = 1;
  nacti();
};

window.naStranu = function (n) {
  stav.strana = n;
  nacti();
  window.scrollTo(0, 0);
};

document.querySelectorAll("th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    if (stav.dotaz) return;               // ve vysledcich radi relevance, ne sloupec
    const s = th.dataset.sort;
    stav.smer = stav.razeni === s && stav.smer === "asc" ? "desc" : "asc";
    stav.razeni = s;
    stav.strana = 1;
    nacti();
  });
});

$("form").addEventListener("submit", (e) => {
  e.preventDefault();                     // resi i Enter v poli
  const q = $("dotaz").value.trim();
  stav.dotaz = q || null;
  stav.sekce = $("sekce").value;
  stav.strana = 1;
  nacti();
});

$("btn-reset").addEventListener("click", () => {
  $("dotaz").value = "";
  $("sekce").value = "";
  stav.dotaz = null;
  stav.sekce = "";
  stav.prah = PRAH_VYCHOZI;
  prahEl.value = PRAH_VYCHOZI;
  prahOut.textContent = PRAH_VYCHOZI.toFixed(2);
  stav.strana = 1;
  stav.razeni = "nazev";
  stav.smer = "asc";
  $("router").hidden = true;
  $("atc-navrh").hidden = true;
  nacti();
});


// Posun jen prekresluje cislo; hledat se jde az pri pusteni mysi (change),
// jinak by kazdy krok posuvniku poslal dotaz na model.
prahEl.addEventListener("input", () => {
  prahOut.textContent = Number(prahEl.value).toFixed(2);
});
prahEl.addEventListener("change", () => {
  stav.prah = Number(prahEl.value);
  if (stav.dotaz) { stav.strana = 1; nacti(); }
});
jistotaEl.addEventListener("input", () => {
  jistotaOut.textContent = Number(jistotaEl.value).toFixed(2);
  prebarvi();                       // hned, bez dotazu na server
});

$("btn-prah-vychozi").addEventListener("click", () => {
  prahEl.value = PRAH_VYCHOZI;
  prahOut.textContent = PRAH_VYCHOZI.toFixed(2);
  stav.prah = PRAH_VYCHOZI;
  if (stav.dotaz) { stav.strana = 1; nacti(); }
});

$("sekce").addEventListener("change", () => {
  if (stav.dotaz) { stav.sekce = $("sekce").value; stav.strana = 1; nacti(); }
});

// --- start ------------------------------------------------------------------
(async function () {
  await pockejNaModely();
  nacti();
})();
