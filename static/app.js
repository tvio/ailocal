"use strict";

// Stav obrazovky. `dotaz === null` znamena uvodni vypis leciv, jinak vysledky
// hledani - obojI se kresli TOUZ funkci, protoze API vraci stejny tvar.
const PRAH_VYCHOZI = 0.55;   // namerena hodnota, viz evaluate.py --prahy
const stav = { dotaz: null, sekce: "", prah: PRAH_VYCHOZI,
               strana: 1, razeni: "nazev", smer: "asc" };

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
        "&prah=" + stav.prah + (stav.sekce ? "&sekce=" + stav.sekce : "")
      : "/api/leciva?strana=" + stav.strana + "&razeni=" + stav.razeni + "&smer=" + stav.smer;

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
  $("telo").innerHTML = d.radky.map((r, i) => radek(r, i, d.cely_usek, d.usek_orezan)).join("");
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
    nalez = '<span class="nalez">' + esc(n.obsah_text) +
      (n.frekvence ? '<span class="znacka">' + esc(n.frekvence) + "</span>" : "") +
      (n.skupina ? '<span class="znacka">' + esc(n.skupina) + "</span>" : "") +
      '<span class="znacka">' + esc(n.sekce_nazev) + "</span></span>";
  }

  // U cteni sekce ("davkovani zyrtec") se vraci CELA sekce, ne serazeny
  // vyber - at je videt, ze zbytek je v rozbaleni a ne ze chybi.
  if (celyUsek && r.dalsi && r.dalsi.length) {
    // Kdyz sekci zuzil dalsi filtr, NENI to cela sekce - 6 polozek ze 44.
    nalez += ' <span class="znacka">' +
             (orezan ? "odpovídá filtru: " : "celá sekce, ") +
             (r.dalsi.length + 1) + " položek — rozbalte ▼</span>";
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
    '<td class="nazev">' + esc(l.nazev) + "</td>" +
    "<td>" + esc(l.sila) + "</td>" +
    "<td>" + esc((l.ucinne_latky || []).join(", ")) + "</td>" +
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

  let h = "<dl>" +
    "<dt>Kód SÚKL</dt><dd>" + esc(l.kod_sukl) + "</dd>" +
    "<dt>Léková forma</dt><dd>" + (l.lekova_forma ? esc(l.lekova_forma) : "—") + "</dd>" +
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
    "</dl>";

  if (r.dalsi && r.dalsi.length) {
    h += "<h4>" + (!celyUsek ? "Další nalezené pasáže"
                   : orezan ? "Položky odpovídající filtru (pořadí podle dokumentu)"
                   : "Celá sekce (pořadí podle dokumentu)") + "</h4><ul>" +
      r.dalsi.map((d) =>
        "<li>" + esc(d.obsah_text) + ' <span class="tise">(' + esc(d.sekce_nazev) +
        (d.cosine !== null && d.cosine !== undefined ? ", cosine " + d.cosine.toFixed(3) : "") +
        ")</span></li>").join("") + "</ul>";
  }
  return h;
}

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

function vykresliStrankovani(d) {
  const el = $("strankovani");
  if (d.stran <= 1) {
    el.innerHTML = '<span class="tise">' + d.celkem + " záznamů</span>";
    return;
  }
  const b = [];
  b.push("<button " + (d.strana <= 1 ? "disabled" : "") +
         ' onclick="naStranu(' + (d.strana - 1) + ')">&lsaquo;</button>');
  for (let i = 1; i <= d.stran; i++) {
    b.push('<button class="' + (i === d.strana ? "aktivni" : "") +
           '" onclick="naStranu(' + i + ')">' + i + "</button>");
  }
  b.push("<button " + (d.strana >= d.stran ? "disabled" : "") +
         ' onclick="naStranu(' + (d.strana + 1) + ')">&rsaquo;</button>');
  b.push('<span class="tise">' + d.celkem + " záznamů, " + d.na_strance + " na stránku</span>");
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
  const sipka = tr.querySelector(".sipka");
  if (sipka) sipka.setAttribute("aria-expanded", String(!r.hidden));
};

window.otevriPdf = function (kod, strana) {
  // Fragment #page=N umi vestaveny prohlizec PDF - otevre se rovnou u pasaze.
  window.open("/api/pdf/" + kod + (strana ? "#page=" + strana : ""), "_blank");
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
